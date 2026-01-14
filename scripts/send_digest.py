import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from typing import List, Dict
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


BASE_URL = os.getenv(
    "SCHOLARSHIP_URL",
    "https://janghak.khu.ac.kr/janghak/user/bbs/BMSR00040/list.do",
)
CATEGORY_PREFIXES = ("공통_", "국제_")
REQUEST_TIMEOUT = 30
DEFAULT_MENU_NO = "12300032"


def fetch_list(session: requests.Session) -> List[Dict[str, str]]:
    """Fetch list page and filter rows matching desired categories."""
    resp = session.get(BASE_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    rows = soup.select("table tbody tr")
    items: List[Dict[str, str]] = []

    for row in rows:
        link = row.find("a", href=True)
        if not link:
            continue

        cells = row.find_all("td")

        category = None
        for selector in [".bbs_cate", ".board_cate", ".category"]:
            node = row.select_one(selector)
            if node:
                category = node.get_text(strip=True)
                break
        # 테이블 구조: 0=번호, 1=카테고리인 경우가 많으므로 우선 1번 칸을 사용
        if not category and len(cells) > 1:
            category = cells[1].get_text(strip=True)
        elif not category and cells:
            category = cells[0].get_text(strip=True)
        if not category:
            continue
        if not category.startswith(CATEGORY_PREFIXES):
            continue

        title = link.get_text(strip=True)
        url = build_detail_url(link.get("href", ""))
        posted_at = cells[-1].get_text(strip=True) if cells else ""

        items.append(
            {
                "title": title,
                "category": category,
                "url": url,
                "posted_at": posted_at,
            }
        )

    return items


def build_detail_url(href: str) -> str:
    """Convert a javascript:view('id') href to a real detail URL."""
    href = (href or "").strip()
    if href.startswith("javascript:view"):
        article_id = "".join(ch for ch in href if ch.isdigit())
        if article_id:
            parsed = urlparse(BASE_URL)
            qs = parse_qs(parsed.query)
            menu_no = qs.get("menuNo", [DEFAULT_MENU_NO])[0]
            base = BASE_URL.split("list.do")[0]
            return f"{base}view.do?articleId={article_id}&menuNo={menu_no}"
    if href.startswith("http"):
        return href
    return urljoin(BASE_URL, href)


def fetch_detail(session: requests.Session, url: str) -> str:
    """Fetch a detail page and return cleaned text content."""
    resp = session.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for node in soup.select(
        ".bbs_cont, .view_cnt, .board_view, .bd_content, .contents"
    ):
        text = node.get_text("\n", strip=True)
        if text:
            return text

    body = soup.find("body")
    return body.get_text("\n", strip=True) if body else ""


def build_email_body(items: List[Dict[str, str]], fetched_at: datetime) -> str:
    lines: List[str] = []
    lines.append(f"경희대 장학 공지 (공통_/국제_) {fetched_at:%Y-%m-%d %H:%M}")
    lines.append(f"총 {len(items)}건\n")

    if not items:
        lines.append("금일 신규로 확인된 공지가 없습니다.")
        return "\n".join(lines)

    for idx, item in enumerate(items, start=1):
        lines.append(f"[{idx}] {item['title']}")
        lines.append(f"카테고리: {item['category']}")
        if item.get("posted_at"):
            lines.append(f"등록일: {item['posted_at']}")
        lines.append(f"링크: {item['url']}")

        detail = item.get("detail", "").strip()
        if detail:
            preview = detail if len(detail) <= 1200 else f"{detail[:1200]}..."
            lines.append("내용 요약:")
            lines.append(preview)
        lines.append("")

    return "\n".join(lines)


def send_email(body: str, subject: str) -> None:
    required_env = [
        "EMAIL_HOST",
        "EMAIL_PORT",
        "EMAIL_USERNAME",
        "EMAIL_PASSWORD",
        "EMAIL_FROM",
        "EMAIL_TO",
    ]
    missing = [key for key in required_env if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Missing required email settings: {', '.join(missing)}")

    host = os.environ["EMAIL_HOST"]
    port = int(os.environ.get("EMAIL_PORT", "587"))
    username = os.environ["EMAIL_USERNAME"]
    password = os.environ["EMAIL_PASSWORD"]
    sender = os.environ["EMAIL_FROM"]
    recipient = os.environ["EMAIL_TO"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls(context=context)
        smtp.login(username, password)
        smtp.send_message(msg)


def main() -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": "khu-scholarship-agent/1.0"})

    items = fetch_list(session)
    for item in items:
        try:
            item["detail"] = fetch_detail(session, item["url"])
        except Exception as exc:  # noqa: BLE001
            item["detail"] = f"내용을 가져오지 못했습니다: {exc}"

    now = datetime.now()
    subject = f"[경희대] 장학 공지 요약 ({now:%Y-%m-%d})"
    body = build_email_body(items, fetched_at=now)
    send_email(body, subject)


if __name__ == "__main__":
    main()
