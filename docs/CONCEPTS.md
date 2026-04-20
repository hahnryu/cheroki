# Concepts

cheroki를 이해하고 운영하는 데 필요한 배경 지식.

## SQLite

파일 한 개짜리 관계형 DB. Python 내장이라 별도 서버·설치 불필요.

- **위치**: `data/siltare.db` (기본)
- **조작**: `sqlite3 data/siltare.db`로 CLI 진입, 또는 GUI (DB Browser for SQLite)
- **백업**: `.db` 파일을 그대로 복사하면 끝
- **스키마**: [PLAN_v3.md](PLAN_v3.md)의 8절 참고. `transcripts` 테이블 하나.

왜 SQLite?
- 사용자 수 명 규모에는 충분
- 의존성이 적음 (서버 프로세스 관리 없음)
- 나중에 PostgreSQL로 마이그레이션 쉬움 (`transcripts` 테이블 하나뿐)

3단계(실타래 본체 통합)에서 PostgreSQL로 이관 예정.

## Docker / Docker Compose

컨테이너 기반 실행 도구. 호스트 OS와 격리된 환경에서 소프트웨어를 돌린다.

cheroki에서는 **Local Bot API 서버(`tdlib/telegram-bot-api` 컨테이너)** 하나만 Docker로 띄운다. Python은 호스트에서 직접 실행.

필수 명령어 3개:
```bash
docker compose up -d       # 백그라운드 시작
docker compose down        # 중지 + 제거
docker compose logs -f     # 실시간 로그
```

## Local Bot API Server

Telegram이 공식 제공하는 Bot API는 **파일 수신 20MB 제한**이 있다. 하회 morning walk 같은 1~2시간 녹음(수백 MB)은 그냥 못 받는다.

[`tdlib/telegram-bot-api`](https://github.com/tdlib/telegram-bot-api)는 이 Bot API 서버의 **자체 호스팅 버전**이고, **최대 2GB까지 수신** 가능하다.

구조:
```
사용자 Telegram 앱
     ↓ 파일 전송
Telegram 서버 (MTProto)
     ↓
Local Bot API 서버 (우리 Docker 컨테이너, localhost:8081)
     ↓
cheroki 봇 (Python, 호스트)
```

봇의 HTTP 요청(`bot.send_message(...)`, `bot.download(...)`)이 원래 `https://api.telegram.org`로 나가야 할 것을, 우리 컨테이너의 `http://localhost:8081`로 가도록 aiogram에 설정해준다.

`TELEGRAM_API_ID`/`HASH`가 필요한 이유: Local Bot API 서버는 MTProto(Telegram 내부 프로토콜)로 본 Telegram 서버와 통신하며, 이는 앱 수준 인증을 요구한다. <https://my.telegram.org>에서 발급.

## aiogram v3

Python용 Telegram 봇 프레임워크. async 친화적.

핵심 개념:
- **Bot**: Telegram API 클라이언트 인스턴스
- **Dispatcher**: 들어오는 업데이트(메시지 등)를 핸들러로 라우팅
- **Router**: 핸들러 묶음. Dispatcher에 include
- **Filters**: 어떤 메시지에 반응할지 (`F.audio`, `Command("help")` 등)
- **`workflow_data`**: Dispatcher에 넣어둔 의존성을 핸들러 인자로 자동 주입

cheroki에서는 `dp["db"] = SQLiteStore(...)` 식으로 넣고, 핸들러 시그니처에 `db: SQLiteStore`로 받으면 aiogram이 알아서 넣어준다.

이전 cheroki는 `python-telegram-bot` v20을 썼다. aiogram v3가 더 async-native하고 DI 패턴이 깔끔해서 새로 골랐다.

## Deepgram

음성 → 텍스트 SaaS. Nova-2 모델이 한국어 + 화자분리 + 타임스탬프를 한 번에 제공한다.

cheroki는 Deepgram의 **prerecorded API** (v1/listen)에 오디오 바이트를 POST하고 JSON 응답을 받는다. 요청 파라미터:
- `model=nova-2`
- `language=ko`
- `diarize=true` (화자분리)
- `utterances=true` (발화 단위 분절)
- `punctuate=true`, `smart_format=true`

응답 JSON의 `results.utterances[*]`에서 `{speaker, start, end, transcript, confidence}`를 꺼내 우리의 `Utterance` 데이터 클래스로 매핑한다. 원본 응답은 `data/exports/<id>.raw.json`에 통째로 저장 (재처리/디버깅용).

Whisper 대비 장점:
- 빠름 (30분 파일 ~10초 처리)
- 화자분리 + 타임스탬프 기본 제공
- 클라우드라 로컬 GPU 불필요
- 싸다 (분당 약 11원, $200 크레딧으로 ~750시간)

단점:
- 음성 원본이 Deepgram 서버로 나감 (프라이버시 고려 대상)
- 네트워크 필요

3단계에서 민감한 녹음용 로컬 Whisper fallback을 추가할 수도 있다 (`transcribers/whisper.py` placeholder).

## SRT 포맷

자막 파일 표준. 미디어 플레이어(VLC, QuickTime, IINA 등)가 동영상 옆에 두면 자동 인식한다.

```
1
00:00:00,000 --> 00:00:03,250
S0: 안녕하세요

2
00:00:03,500 --> 00:00:07,800
S1: 네, 반갑습니다
```

- 번호 → 시작타임 `-->` 끝타임 → 본문 → 빈 줄
- 타임스탬프는 `HH:MM:SS,mmm` (콤마로 ms 구분)
- 화자는 본문 앞에 `S0:`, `S1:` 접두어로 표기

## 화자분리 (Diarization)

"이 오디오를 두 사람이 번갈아 말한다면, 각 발화를 어느 사람(스피커 0/1/2)에게 귀속시킬 것인가"를 푸는 문제. Deepgram이 AI로 자동 처리.

주의:
- 같은 사람이라도 중간에 기침하거나 소리 끊기면 다른 스피커로 잘못 묶일 수 있음
- 세 명 이상 동시 대화는 정확도 떨어짐
- 이름은 `S0`, `S1`으로만 나온다. "이 스피커 0이 류중하입니다"는 후처리 필요 (2단계)

## 6자리 base32 short ID

각 녹취에 `ab7f3c` 같은 6자리 ID를 붙인다. Crockford base32 알파벳(`0-9a-z` 중 혼동 쉬운 i, l, o, u 제외)을 쓴다.

- 조합 수: 32⁶ = 약 10.7억
- 충돌 가능성: 10만 건이 쌓여도 무시 가능 수준
- 용도:
  - 저장 파일명: `data/uploads/ab7f3c.m4a`, `data/exports/ab7f3c.srt`
  - Telegram 명령어: `/get ab7f3c`, `/status ab7f3c`
  - SQLite 기본키

UUID(36자)는 너무 길어서 Telegram 메시지에서 말하기 불편하다. 6자리면 사람이 소리내어 읽을 수도 있다.
