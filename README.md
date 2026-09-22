# 경희대 장학 공지 에이전트

경희대학교 미래혁신단 학생지원센터(장학)에 올라오는 공통_ 또는 국제_로 시작하는 최근 5일의 장학 카테고리 공지를 매일 오전 9시경(한국시간)에 수집해 이메일로 보내는 GitHub Actions 워크플로우입니다.

- 경희대학교 미래혁신단 학생지원센터(장학) 링크: https://janghak.khu.ac.kr/janghak/user/bbs/BMSR00040/list.do?menuNo=12300032

## 구성
- `scripts/send_digest.py`: 공지 크롤링 및 이메일 발송 스크립트.
- `.github/workflows/daily-digest.yml`: 매일 오전 9시경(한국시간)에 실행되는 스케줄러.
- `requirements.txt`: Python 의존성 목록.

## 설정 방법
1) 해당 GitHub 리포지토리를 Fork 하여 자신의 계정으로 복사합니다.
2) GitHub 저장소 Settings → Secrets and variables → Actions에 다음 시크릿을 등록합니다:
   - `EMAIL_HOST`: SMTP 서버 호스트 (Gmail의 경우 `smtp.gmail.com`)
   - `EMAIL_PORT`: SMTP 포트 (Gmail의 경우 `587`)
   - `EMAIL_USERNAME`: SMTP 로그인 계정 (발신자 Gmail 주소)
   - `EMAIL_PASSWORD`: SMTP 비밀번호 또는 앱 비밀번호
     - **Gmail 앱 비밀번호 생성 방법**:
       1. Google 계정 관리 페이지 접속 ([myaccount.google.com](https://myaccount.google.com/))
       2. 왼쪽 메뉴에서 **보안** 클릭
       3. 'Google에 로그인하는 방법' 섹션에서 **2단계 인증**이 사용 중인지 확인 (필수)
       4. 2단계 인증 섹션 내에서 **앱 비밀번호** 클릭 (로그인이 필요할 수 있음)
       5. '앱 선택'에서 **메일**을 선택하고, '기기 선택'에서 **기타(맞춤 이름)**를 선택 후 적절한 이름(예: `khu-scholarship-agent`) 입력
       6. **생성** 버튼을 클릭하면 16자리의 앱 비밀번호가 생성됩니다. 이 비밀번호를 복사하여 `EMAIL_PASSWORD` 시크릿에 붙여넣기
   - `EMAIL_FROM`: 발신자 이메일 주소 (Gmail 주소와 동일하게 설정)
   - `EMAIL_TO`: 기본 수신자 이메일 주소
   - `EMAIL_TO_ADDITIONAL`: 추가 수신자 이메일 주소
     - 쉼표(`,`) 또는 세미콜론(`;`)으로 여러 주소를 지정할 수 있습니다.
     - 각 수신자에게 개별 발송하므로 다른 수신자의 주소는 노출되지 않습니다.
   - `EMAIL_UNSUBSCRIBE_SECRET`: 수신 거부 링크 서명에 사용할 충분히 긴 임의 문자열
     - 한 번 설정한 뒤 변경하지 마세요. 변경하면 이전 메일의 수신 거부 링크가 무효화됩니다.
   - `EMAIL_IMAP_HOST` (선택): 수신 거부 요청을 확인할 IMAP 호스트
     - Gmail SMTP(`smtp.gmail.com`) 사용 시 비워 두면 `imap.gmail.com`을 자동 사용합니다.
   - `EMAIL_IMAP_PORT` (선택): IMAP SSL 포트 (기본값 `993`)
   - `SCHOLARSHIP_URL` (선택): 기본 공지 URL을 변경하려면 설정 (현재 `https://janghak.khu.ac.kr/janghak/user/bbs/BMSR00040/list.do?menuNo=12300032`)

3) 워크플로우가 `Asia/Seoul` 시간대 기준 매일 오전 9시경에 실행됩니다. 다른 시간이 필요하면 `.github/workflows/daily-digest.yml`의 cron을 수정하세요.

## 로컬 테스트
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
EMAIL_HOST=... EMAIL_PORT=587 EMAIL_USERNAME=... EMAIL_PASSWORD=... EMAIL_FROM=... EMAIL_TO=... EMAIL_TO_ADDITIONAL=... EMAIL_UNSUBSCRIBE_SECRET=... python scripts/send_digest.py
```

## 동작 개요
- 목록 페이지에서 카테고리가 공통_/국제_로 시작하는 행만 필터링합니다.
- 수집된 공지가 없으면 “금일 신규로 확인된 공지가 없습니다.” 메시지를 보냅니다.
- 각 메일 하단에 수신 거부 버튼을 표시하고 표준 `List-Unsubscribe` 헤더를 함께 보냅니다.
- 수신자가 버튼을 누른 뒤 생성된 수신 거부 메일을 보내면, 다음 실행부터 해당 주소만 자동 제외합니다.
- 수신 거부 요청은 서명된 토큰으로 검증하며, 발신 계정의 IMAP 받은편지함을 수신 거부 목록으로 사용합니다.
- GitHub Actions 실행 요약에서 `기본 수신자`, `추가 수신자`별 SMTP 접수 성공·실패·수신 거부 제외 상태를 확인할 수 있습니다. 실제 이메일 주소는 공개 로그에 표시하지 않습니다.
