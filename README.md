# 경희대 장학 공지 에이전트

공통_ 또는 국제_로 시작하는 장학 카테고리 공지를 매일 09:00(한국시간)에 수집해 이메일로 보내는 GitHub Actions 워크플로우입니다.

## 구성
- `scripts/send_digest.py`: 공지 크롤링 및 이메일 발송 스크립트.
- `.github/workflows/daily-digest.yml`: 매일 09:00 KST에 실행되는 스케줄러.
- `requirements.txt`: Python 의존성 목록.

## 설정 방법
1) 리포지토리를 GitHub에 푸시합니다.  
2) GitHub 저장소 Settings → Secrets and variables → Actions에 다음 시크릿을 등록합니다:
   - `EMAIL_HOST`: SMTP 서버 호스트 (예: smtp.gmail.com)
   - `EMAIL_PORT`: SMTP 포트 (예: 587)
   - `EMAIL_USERNAME`: SMTP 로그인 계정
   - `EMAIL_PASSWORD`: SMTP 비밀번호 또는 앱 비밀번호
   - `EMAIL_FROM`: 발신자 이메일 주소
   - `EMAIL_TO`: 수신자 이메일 주소
   - `SCHOLARSHIP_URL` (선택): 기본 공지 URL을 변경하려면 설정

3) 워크플로우가 기본으로 00:00 UTC(09:00 KST)에 실행됩니다. 다른 시간대가 필요하면 `.github/workflows/daily-digest.yml`의 cron을 수정하세요.

## 로컬 테스트
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
EMAIL_HOST=... EMAIL_PORT=587 EMAIL_USERNAME=... EMAIL_PASSWORD=... EMAIL_FROM=... EMAIL_TO=... python scripts/send_digest.py
```

## 동작 개요
- 목록 페이지에서 카테고리가 공통_/국제_로 시작하는 행만 필터링합니다.
- 각 글의 상세 페이지를 열어 본문을 함께 메일 본문에 포함합니다.
- 수집된 공지가 없으면 “금일 신규로 확인된 공지가 없습니다.” 메시지를 보냅니다.
