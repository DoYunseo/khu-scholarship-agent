import os
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import List, Dict
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


BASE_URL = os.getenv(
    "SCHOLARSHIP_URL",
    "https://janghak.khu.ac.kr/janghak/user/bbs/BMSR00040/list.do?menuNo=12300032",
)
CATEGORY_PREFIXES = ("공통_", "국제_")
REQUEST_TIMEOUT = 30
DEFAULT_MENU_NO = "12300032"
KST = timezone(timedelta(hours=9))


def fetch_list(session: requests.Session) -> List[Dict[str, str]]:
    """Fetch list page and filter rows matching desired categories."""
    print(f"[DEBUG] Fetching list from: {BASE_URL}")
    resp = session.get(BASE_URL, timeout=REQUEST_TIMEOUT)
    print(f"[DEBUG] List page response status: {resp.status_code}")
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 여러 선택자 시도
    rows = None
    for selector in ["#noticeTbody tr", "table tbody tr", "tbody tr", ".board_list tbody tr"]:
        found = soup.select(selector)
        if found:
            rows = found
            print(f"[DEBUG] Using selector '{selector}': found {len(rows)} rows")
            break
    
    if not rows:
        print("[DEBUG] No rows found with any selector!")
        return []
    
    print(f"[DEBUG] Processing {len(rows)} rows")
    items: List[Dict[str, str]] = []
    skipped_categories = []

    for row in rows:
        # 헤더 행(th) 무시
        if row.find("th"):
            continue

        link = row.find("a", href=True)
        if not link:
            continue

        cells = row.find_all("td")
        if not cells:
            continue

        category = None
        potential_category = None

        # 1. 우선적으로 td[1]에서 카테고리 텍스트 추출 시도
        if len(cells) > 1:
            potential_category = cells[1].get_text(strip=True)
            if potential_category and potential_category != "공지": # '공지'는 실제 카테고리가 아님
                category = potential_category
        
        # 2. td[1]에서 유효한 카테고리를 찾지 못했다면, CSS 선택자로 찾기 시도
        if not category:
            for selector in [".bbs_cate", ".board_cate", ".category", "[class*='cate']"]:
                node = row.select_one(selector)
                if node:
                    potential_category = node.get_text(strip=True)
                    if potential_category and potential_category != "공지":
                        category = potential_category
                        break
        
        # 3. 여전히 카테고리를 찾지 못했다면, td[0]에서 최종 시도 (단, '공지'는 제외)
        if not category and len(cells) > 0:
            potential_category = cells[0].get_text(strip=True)
            if potential_category and potential_category != "공지":
                category = potential_category

        if not category:
            continue
        # 공통_ 또는 국제_로 시작하는지 확인
        if not any(category.startswith(prefix) for prefix in CATEGORY_PREFIXES):
            skipped_categories.append(category)
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

    print(f"[DEBUG] Filtered {len(items)} items matching 공통_/국제_")
    if skipped_categories:
        unique_skipped = set(skipped_categories)
        print(f"[DEBUG] Skipped categories: {', '.join(sorted(unique_skipped)[:10])}")
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


def build_email_body(items: List[Dict[str, str]], fetched_at: datetime) -> str:
    lines: List[str] = []
    lines.append(f"경희대 장학 공지 (공통_/국제_, 최근 5일) {fetched_at:%Y-%m-%d %H:%M}")
    lines.append(f"총 {len(items)}건\n")
    lines.append(f"목록 바로가기: {BASE_URL}\n")

    if not items:
        lines.append("최근 5일 이내 공통_/국제_ 카테고리 공지가 없습니다.")
        return "\n".join(lines)

    for idx, item in enumerate(items, start=1):
        lines.append(f"[{idx}] {item['title']}")
        lines.append(f"카테고리: {item['category']}")
        if item.get("posted_at"):
            lines.append(f"등록일: {item['posted_at']}")
        lines.append(f"링크: {item['url']}")
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
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })

    items = fetch_list(session)

    # 최근 5일 이내 공지만 남기기 (KST 기준, 오늘 포함)
    # 예: 오늘이 1월 15일이면 1월 11일~15일 (5일)
    cutoff = datetime.now(KST).date() - timedelta(days=4)
    print(f"[DEBUG] Date filter: including announcements from {cutoff} onwards")
    recent_items: List[Dict[str, str]] = []
    date_parse_errors = 0
    for item in items:
        date_str = (item.get("posted_at") or "").strip()
        if not date_str:
            # 날짜가 없으면 일단 포함
            recent_items.append(item)
            continue
        try:
            posted_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            if posted_date >= cutoff:
                recent_items.append(item)
        except ValueError:
            # 날짜 파싱이 안 되면 일단 포함
            date_parse_errors += 1
            recent_items.append(item)

    print(f"[DEBUG] After date filter: {len(recent_items)} items (date parse errors: {date_parse_errors})")
    items = recent_items

    now = datetime.now(KST)
    subject = f"[경희대] 장학 공지 요약 ({now:%Y-%m-%d})"
    body = build_email_body(items, fetched_at=now)
    send_email(body, subject)


if __name__ == "__main__":
    main()
