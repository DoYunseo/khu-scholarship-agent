"""로컬에서 크롤링이 정상 동작하는지 확인하는 간단한 테스트 스크립트."""
from datetime import datetime

import requests

from send_digest import BASE_URL, fetch_detail, fetch_list


def main() -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": "khu-scholarship-agent/test"})

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 목록 크롤링 시작")
    items = fetch_list(session)
    print(f"필터된 항목: {len(items)}건")

    if not items:
        return

    # 앞부분 몇 개만 상세를 확인해 본다.
    sample = items[:3]
    for idx, item in enumerate(sample, start=1):
        print(f"\n[{idx}] {item['category']} - {item['title']}")
        print(f"URL: {item['url']}")
        try:
            detail = fetch_detail(session, item["url"])
            preview = detail if len(detail) <= 400 else detail[:400] + "..."
            print("본문 미리보기:")
            print(preview)
        except Exception as exc:  # noqa: BLE001
            print(f"본문 수집 실패: {exc}")


if __name__ == "__main__":
    main()
