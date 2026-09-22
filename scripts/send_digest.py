import base64
import hashlib
import hmac
import html
import imaplib
import os
import re
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import EmailMessage
from typing import Dict, List, Optional, Set
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse

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
UNSUBSCRIBE_SUBJECT_PREFIX = "KHU-SCHOLARSHIP-UNSUBSCRIBE"


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
        lines.append("")

    return "\n".join(lines)


def parse_recipients(*values: Optional[str]) -> List[str]:
    """Parse, normalize, and deduplicate comma/semicolon separated recipients."""
    recipients: List[str] = []
    seen: Set[str] = set()
    for value in values:
        for recipient in re.split(r"[,;\n]", value or ""):
            recipient = recipient.strip().lower()
            if recipient and recipient not in seen:
                seen.add(recipient)
                recipients.append(recipient)
    return recipients


def build_recipient_entries(
    primary: Optional[str], additional: Optional[str]
) -> List[Dict[str, str]]:
    """Build privacy-safe labels for recipients without exposing addresses in logs."""
    entries: List[Dict[str, str]] = []
    seen: Set[str] = set()
    for group_label, value in (
        ("기본 수신자", primary),
        ("추가 수신자", additional),
    ):
        group_index = 0
        for recipient in parse_recipients(value):
            if recipient in seen:
                continue
            seen.add(recipient)
            group_index += 1
            entries.append(
                {"address": recipient, "label": f"{group_label} {group_index}"}
            )
    return entries


def create_unsubscribe_token(recipient: str, secret: str) -> str:
    """Create a tamper-proof bearer token for one recipient."""
    encoded_recipient = base64.urlsafe_b64encode(
        recipient.strip().lower().encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(
        secret.encode("utf-8"), encoded_recipient.encode("ascii"), hashlib.sha256
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{encoded_recipient}.{encoded_signature}"


def recipient_from_unsubscribe_token(token: str, secret: str) -> Optional[str]:
    """Return the recipient encoded in a valid unsubscribe token."""
    try:
        encoded_recipient, supplied_signature = token.strip().split(".", 1)
        expected_signature = hmac.new(
            secret.encode("utf-8"), encoded_recipient.encode("ascii"), hashlib.sha256
        ).digest()
        expected = base64.urlsafe_b64encode(expected_signature).decode("ascii").rstrip("=")
        if not hmac.compare_digest(supplied_signature, expected):
            return None
        padding = "=" * (-len(encoded_recipient) % 4)
        return base64.urlsafe_b64decode(encoded_recipient + padding).decode("utf-8").lower()
    except (UnicodeDecodeError, ValueError):
        return None


def build_unsubscribe_url(sender: str, recipient: str, secret: str) -> str:
    """Build a mailto unsubscribe URL understood by common email clients."""
    token = create_unsubscribe_token(recipient, secret)
    query = urlencode(
        {
            "subject": f"{UNSUBSCRIBE_SUBJECT_PREFIX} {token}",
            "body": "이 메일을 그대로 보내면 경희대 장학 공지 메일 수신이 거부됩니다.",
        }
    )
    return f"mailto:{quote(sender, safe='@')}?{query}"


def build_html_body(body: str, unsubscribe_url: str) -> str:
    """Create the HTML alternative with an unsubscribe button at the bottom."""
    escaped_body = html.escape(body).replace("\n", "<br>\n")
    escaped_url = html.escape(unsubscribe_url, quote=True)
    return f"""<!doctype html>
<html lang="ko">
  <body style="font-family: Arial, 'Noto Sans KR', sans-serif; color: #202124; line-height: 1.6;">
    <div>{escaped_body}</div>
    <div style="margin-top: 32px; padding-top: 18px; border-top: 1px solid #dadce0; color: #5f6368; font-size: 12px;">
      더 이상 이 안내를 받고 싶지 않다면 아래 버튼을 누른 뒤 수신 거부 메일을 보내 주세요.<br>
      <a href="{escaped_url}" style="display: inline-block; margin-top: 10px; padding: 8px 14px; border: 1px solid #9aa0a6; border-radius: 4px; color: #5f6368; text-decoration: none;">수신 거부</a>
    </div>
  </body>
</html>"""


def infer_imap_host(smtp_host: str) -> str:
    """Infer the common IMAP hostname while allowing an explicit override."""
    if smtp_host.lower().startswith("smtp."):
        return f"imap.{smtp_host[5:]}"
    return smtp_host


def find_unsubscribed_recipients(
    host: str,
    port: int,
    username: str,
    password: str,
    secret: str,
) -> Set[str]:
    """Read signed unsubscribe requests from the sender's inbox."""
    unsubscribed: Set[str] = set()
    context = ssl.create_default_context()
    with imaplib.IMAP4_SSL(host, port, ssl_context=context) as mailbox:
        mailbox.login(username, password)
        status, _ = mailbox.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError("Could not open the IMAP inbox")

        status, data = mailbox.search(
            None, "HEADER", "Subject", f'"{UNSUBSCRIBE_SUBJECT_PREFIX}"'
        )
        if status != "OK":
            raise RuntimeError("Could not search for unsubscribe requests")

        for message_id in data[0].split():
            status, parts = mailbox.fetch(message_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
            if status != "OK":
                continue
            header_bytes = next(
                (part[1] for part in parts if isinstance(part, tuple) and part[1]), None
            )
            if not header_bytes:
                continue
            message = message_from_bytes(header_bytes)
            subject = str(make_header(decode_header(message.get("Subject", ""))))
            match = re.search(
                rf"{re.escape(UNSUBSCRIBE_SUBJECT_PREFIX)}\s+([^\s]+)", subject
            )
            if not match:
                continue
            recipient = recipient_from_unsubscribe_token(match.group(1), secret)
            if recipient:
                unsubscribed.add(recipient)

    return unsubscribed


def write_delivery_summary(results: List[Dict[str, str]]) -> None:
    """Append a per-recipient delivery table to the GitHub Actions run summary."""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as summary:
        summary.write("## 이메일 발송 결과\n\n")
        summary.write("| 수신자 | 상태 | 설명 |\n")
        summary.write("|---|---|---|\n")
        for result in results:
            label = result["label"].replace("|", "\\|")
            status = result["status"].replace("|", "\\|")
            detail = result["detail"].replace("|", "\\|")
            summary.write(f"| {label} | {status} | {detail} |\n")


def send_email(body: str, subject: str) -> List[Dict[str, str]]:
    required_env = [
        "EMAIL_HOST",
        "EMAIL_PORT",
        "EMAIL_USERNAME",
        "EMAIL_PASSWORD",
        "EMAIL_FROM",
        "EMAIL_TO",
        "EMAIL_UNSUBSCRIBE_SECRET",
    ]
    missing = [key for key in required_env if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Missing required email settings: {', '.join(missing)}")

    host = os.environ["EMAIL_HOST"]
    port = int(os.environ.get("EMAIL_PORT", "587"))
    username = os.environ["EMAIL_USERNAME"]
    password = os.environ["EMAIL_PASSWORD"]
    sender = os.environ["EMAIL_FROM"]
    secret = os.environ["EMAIL_UNSUBSCRIBE_SECRET"]
    recipient_entries = build_recipient_entries(
        os.environ["EMAIL_TO"], os.getenv("EMAIL_TO_ADDITIONAL")
    )
    if not recipient_entries:
        raise RuntimeError("No email recipients configured")

    imap_host = os.getenv("EMAIL_IMAP_HOST") or infer_imap_host(host)
    imap_port = int(os.getenv("EMAIL_IMAP_PORT") or "993")
    unsubscribed = find_unsubscribed_recipients(
        imap_host, imap_port, username, password, secret
    )
    active_entries = [
        entry for entry in recipient_entries if entry["address"] not in unsubscribed
    ]
    print(
        f"[INFO] Recipients: {len(recipient_entries)}, "
        f"unsubscribed: {len(recipient_entries) - len(active_entries)}, "
        f"sending: {len(active_entries)}"
    )

    results_by_address: Dict[str, Dict[str, str]] = {}
    for entry in recipient_entries:
        if entry["address"] in unsubscribed:
            results_by_address[entry["address"]] = {
                "label": entry["label"],
                "status": "⏭️ 제외",
                "detail": "수신 거부 요청에 따라 발송하지 않음",
            }
            print(f"[DELIVERY] {entry['label']}: SKIPPED (unsubscribed)")

    if not active_entries:
        results = [results_by_address[entry["address"]] for entry in recipient_entries]
        write_delivery_summary(results)
        return results

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(host, port) as smtp:
            smtp.starttls(context=context)
            smtp.login(username, password)
            for entry in active_entries:
                recipient = entry["address"]
                unsubscribe_url = build_unsubscribe_url(sender, recipient, secret)
                msg = EmailMessage()
                msg["Subject"] = subject
                msg["From"] = sender
                msg["To"] = recipient
                msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
                msg.set_content(
                    f"{body}\n\n---\n수신 거부: {unsubscribe_url}\n"
                    "링크를 연 뒤 수신 거부 메일을 보내 주세요. 다음 발송부터 제외됩니다."
                )
                msg.add_alternative(build_html_body(body, unsubscribe_url), subtype="html")
                try:
                    refused = smtp.send_message(msg)
                    if refused:
                        raise smtplib.SMTPRecipientsRefused(refused)
                    results_by_address[recipient] = {
                        "label": entry["label"],
                        "status": "✅ 성공",
                        "detail": "SMTP 서버 접수 완료",
                    }
                    print(f"[DELIVERY] {entry['label']}: SUCCESS (SMTP accepted)")
                except smtplib.SMTPException as exc:
                    results_by_address[recipient] = {
                        "label": entry["label"],
                        "status": "❌ 실패",
                        "detail": f"SMTP 오류 ({type(exc).__name__})",
                    }
                    print(
                        f"[DELIVERY] {entry['label']}: FAILED "
                        f"({type(exc).__name__})"
                    )
    except (OSError, smtplib.SMTPException, ssl.SSLError) as exc:
        for entry in active_entries:
            if entry["address"] not in results_by_address:
                results_by_address[entry["address"]] = {
                    "label": entry["label"],
                    "status": "❌ 실패",
                    "detail": f"SMTP 연결 오류 ({type(exc).__name__})",
                }
                print(
                    f"[DELIVERY] {entry['label']}: FAILED "
                    f"({type(exc).__name__})"
                )

    results = [results_by_address[entry["address"]] for entry in recipient_entries]
    write_delivery_summary(results)
    failed_labels = [result["label"] for result in results if "실패" in result["status"]]
    if failed_labels:
        raise RuntimeError(
            f"Email delivery failed for {len(failed_labels)} recipient(s): "
            + ", ".join(failed_labels)
        )
    return results


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
