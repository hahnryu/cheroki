# Setup

노트북(개발 환경) 기준 초기 설정 가이드. 배포는 [DEPLOY.md](DEPLOY.md).

## 1. 사전 준비

### 1.1 Telegram 봇 토큰

이미 발급된 @cheroki_siltarebot을 사용한다.
`.env`의 `BOT_TOKEN`이 비어 있으면 [@BotFather](https://t.me/BotFather) → `/mybots` → API Token에서 확인.

### 1.2 Telegram API id/hash (Local Bot API 서버용)

2GB 파일 수신을 위해 Local Bot API 서버를 Docker로 돌린다. 이 서버는 `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`가 있어야 기동된다.

1. <https://my.telegram.org>에 본인 번호로 로그인
2. "API development tools" → "Create new application"
3. 앱 이름은 아무거나 (예: "cheroki-dev")
4. 발급된 `api_id`(숫자)와 `api_hash`(32자 문자열)를 `.env`에 기록

> 없어도 Python 라이브러리로는 바로 쓸 수 있음. Telegram 봇으로 대용량 파일을 받을 때만 필요.

### 1.3 Deepgram API 키

1. <https://console.deepgram.com>에서 가입 ($200 크레딧 자동 지급)
2. API Keys → Create New Key
3. `.env`의 `DEEPGRAM_API_KEY`에 붙여넣기

### 1.4 허용 사용자 ID

Telegram에서 [@userinfobot](https://t.me/userinfobot)에 `/start`를 보내면 자기 `user_id`(숫자)가 나온다. 콤마로 구분해 `.env`의 `ALLOWED_USER_IDS`에 기록.

```
ALLOWED_USER_IDS=123456789,987654321
```

비어 있으면 모든 메시지가 거부된다.

## 2. 파이썬 환경

```bash
cd ~/projects/cheroki
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

uv가 없으면:
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 3. 환경변수 파일

```bash
cp .env.example .env
$EDITOR .env
```

최소 필요한 값:
- `BOT_TOKEN`
- `DEEPGRAM_API_KEY`
- `ALLOWED_USER_IDS`

Local Bot API 서버를 돌리려면 추가로:
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`

## 4. 테스트

```bash
pytest
```

21개 테스트가 전부 통과해야 한다.

## 5. 첫 실행

### 5.1 라이브러리로만 쓰기 (Docker 없이)

```python
# quick_test.py
import asyncio
from cheroki import transcribe_audio

async def main():
    result = await transcribe_audio("short_sample.m4a")
    print(result.text)

asyncio.run(main())
```

```bash
python quick_test.py
```

### 5.2 Telegram 봇 돌리기

```bash
# 터미널 1: Local Bot API 서버
docker compose up -d
docker compose logs -f  # 정상 기동 확인

# 터미널 2: 봇
python -m cheroki.interfaces.telegram
```

로그에 `봇 시작: @cheroki_siltarebot (id=...)`이 뜨면 준비 완료.

Telegram에서 허용된 ID로 @cheroki_siltarebot에게 짧은 음성(1분 이하) 하나 전송 → SRT/MD/TXT 3개 파일이 회신되면 end-to-end 성공.

### 5.3 종료

```bash
# 봇: Ctrl+C
# Docker:
docker compose down
```

## 6. 트러블슈팅

### `BOT_TOKEN이 비어 있습니다`
`.env`에 값 입력. 공백 없이.

### `ALLOWED_USER_IDS가 비어 있습니다` 경고 후 메시지 거부
@userinfobot으로 user_id 확인 후 `.env`에 기록. 봇 재시작.

### Deepgram `HTTP 401`
API 키가 잘못됨. Deepgram 콘솔에서 재확인.

### Deepgram `HTTP 400 - Invalid language`
`.env`의 `DEEPGRAM_MODEL`이 nova-2인지 확인. Nova-2는 한국어 완전 지원.

### Local Bot API 서버가 시작 안 됨
`docker compose logs telegram-bot-api`로 로그 확인. `TELEGRAM_API_ID`/`HASH` 미기입이 가장 흔한 원인.

### 봇이 메시지에 응답 없음
1. `.env`의 `BOT_TOKEN` 확인
2. 기존 webhook이 설정되어 있으면 해제:
   ```bash
   curl "https://api.telegram.org/bot$BOT_TOKEN/deleteWebhook"
   ```
3. 다른 곳(이전 cheroki 등)에서 같은 봇 토큰으로 돌고 있지 않은지 확인. Telegram은 같은 토큰을 두 곳에서 동시 폴링 불가.

### 대용량 파일 수신 실패 (`File is too big`)
Local Bot API 서버가 안 켜져 있거나 `.env`의 `LOCAL_API_URL`이 잘못됨. 기본값 `http://localhost:8081` 그대로 쓰고, `docker compose ps`로 서버 상태 확인.

## 7. 다음 단계

- 배포: [DEPLOY.md](DEPLOY.md)
- 개념: [CONCEPTS.md](CONCEPTS.md)
- 로드맵: [PLAN_v3.md](PLAN_v3.md)
