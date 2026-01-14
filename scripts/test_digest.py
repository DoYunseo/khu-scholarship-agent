"""로컬에서 크롤링이 정상 동작하는지 확인하는 간단한 테스트 스크립트."""
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from send_digest import BASE_URL, CATEGORY_PREFIXES, fetch_detail, fetch_list


def debug_table_structure() -> None:
    """테이블 구조를 디버깅하기 위한 함수."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 테이블 구조 디버깅 시작")
    resp = session.get(BASE_URL, timeout=30)
    resp.raise_for_status()
    
    # HTML 응답의 일부를 확인
    print(f"\n응답 상태 코드: {resp.status_code}")
    print(f"응답 길이: {len(resp.text)} bytes")
    print(f"응답의 처음 500자:\n{resp.text[:500]}\n")
    
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # 여러 선택자 시도
    selectors = [
        "#noticeTbody tr",
        "table tbody tr",
        "tbody tr",
        "table tr",
        ".board_list tbody tr",
    ]
    
    for selector in selectors:
        rows = soup.select(selector)
        if rows:
            print(f"\n선택자 '{selector}': {len(rows)}개의 행 발견")
            break
    else:
        print("\n⚠️ 어떤 선택자로도 행을 찾지 못했습니다!")
        print("테이블이 있는지 확인:")
        tables = soup.select("table")
        print(f"  - table 태그 개수: {len(tables)}")
        tbody = soup.select("tbody")
        print(f"  - tbody 태그 개수: {len(tbody)}")
        notice_tbody = soup.select("#noticeTbody")
        print(f"  - #noticeTbody 개수: {len(notice_tbody)}")
        
        # 첫 번째 테이블의 구조 확인
        if tables:
            first_table = tables[0]
            print(f"\n첫 번째 테이블의 자식 요소:")
            for child in first_table.children:
                if hasattr(child, 'name'):
                    print(f"  - {child.name}")
        return
    
    rows = soup.select(selector)
    print(f"\n총 {len(rows)}개의 행 발견\n")
    
    # 처음 5개 행만 상세히 출력
    for i, row in enumerate(rows[:5], 1):
        print(f"=== 행 {i} ===")
        cells = row.find_all("td")
        print(f"총 {len(cells)}개의 td 발견")
        
        for j, cell in enumerate(cells):
            text = cell.get_text(strip=True)
            print(f"  td[{j}]: '{text}'")
        
        # 링크 찾기
        link = row.find("a", href=True)
        if link:
            print(f"  링크 href: '{link.get('href', '')}'")
            print(f"  링크 텍스트: '{link.get_text(strip=True)}'")
        
        # 카테고리 찾기 시도
        category = None
        for selector in [".bbs_cate", ".board_cate", ".category"]:
            node = row.select_one(selector)
            if node:
                category = node.get_text(strip=True)
                print(f"  CSS 선택자 '{selector}'로 찾은 카테고리: '{category}'")
                break
        
        if not category and len(cells) > 1:
            category = cells[1].get_text(strip=True)
            print(f"  td[1]에서 찾은 카테고리: '{category}'")
        elif not category and cells:
            category = cells[0].get_text(strip=True)
            print(f"  td[0]에서 찾은 카테고리: '{category}'")
        
        if category:
            matches = any(category.startswith(prefix) for prefix in CATEGORY_PREFIXES)
            print(f"  필터 조건 ('공통_' 또는 '국제_'로 시작): {matches}")
        print()


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

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 목록 크롤링 시작")
    
    # 먼저 테이블 구조 디버깅
    debug_table_structure()
    
    items = fetch_list(session)
    print(f"\n필터된 항목: {len(items)}건")

    if not items:
        print("\n⚠️ 필터된 항목이 없습니다!")
        print("개발자 모드에서 확인할 사항:")
        print("1. F12로 개발자 도구 열기")
        print("2. Elements 탭에서 테이블 구조 확인")
        print("3. tbody > tr > td 순서 확인 (번호, 카테고리, 제목, 첨부파일, 등록일)")
        print("4. 카테고리가 있는 td의 인덱스(0부터 시작) 확인")
        print("5. 카테고리 텍스트가 정확히 '공통_교외장학' 같은 형식인지 확인")
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
