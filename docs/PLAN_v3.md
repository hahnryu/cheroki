# Cheroki 기획안 v3

> 採錄 · 구술을 채집하고 기록한다.
>
> 실타래 생태계의 STT 모듈. 스탠드얼론 라이브러리로도 작동.

**작성일**: 2026-04-20
**버전**: v3 (최종)
**이전 버전**: v1, v2 (폐기)
**위치**: `~/projects/cheroki/` (노트북) → `hahoe-genesis` (배포)
**봇 계정**: @cheroki_siltarebot
**구현 도구**: Claude Code

---

## 0. 프로젝트 개요

### 한 줄 요약

오디오를 받아 화자분리된 한국어 텍스트로 변환하는 Python 모듈. Telegram 봇 인터페이스 기본 제공.

### 이중 정체성

cheroki는 두 가지 얼굴을 가진다.

1. **라이브러리**: `from cheroki import transcribe_audio` 한 줄로 어디서든 호출 가능한 순수 모듈
2. **Telegram 봇**: 핸드폰으로 오디오 전송 → SRT/MD 파일 수신까지 자동화된 앱

핵심 설계 원칙: **core 모듈이 본체**, Telegram 봇은 그 위에 얹힌 인터페이스일 뿐.

### 배경

**이전 cheroki의 실패** (`d:/projects/cheroki_legacy/`, 2026-03):
- 범위 과대: 전사+교정+산출물+학습+코퍼스+CLI+웹+봇을 한 프로젝트에
- 로컬 Whisper CPU 의존: 30분 파일 10~20분 처리 → 워크플로우 붕괴
- OpenAI API 불안정: verbose_json 미지원, 25MB 제한 우회 삽질
- 뻑 잦음 → 사용 중단

**새 cheroki의 대응**:
- 범위 축소: 전사 + SRT/MD 생성 + Telegram 봇만
- Deepgram API: 안정 + 빠름 + 저렴 ($200 크레딧으로 1년 무료)
- 모듈 분리: core를 순수 라이브러리로, 인터페이스는 복수 지원

---

## 1. 범위

### MVP에서 하는 것

- Telegram 봇 (@cheroki_siltarebot)으로 오디오/비디오 수신 (허용 ID만)
- Local Bot API Server 사용 → 최대 2GB 파일 수신
- Deepgram Nova-2로 한국어 + 화자분리 + 타임스탬프 녹취
- SQLite에 메타데이터 저장 (원본은 파일시스템)
- 완료 시 봇이 SRT + MD + TXT 파일을 Telegram으로 전송
- 처리 상태 조회 (/last, /status, /get)

### MVP에서 안 하는 것

- 웹 UI (FastAPI 없음, 텔레그램에서 완결)
- AI 교정 루프 (2단계)
- 화자 이름 자동 치환 (2단계)
- 실타래 본체 Graphiti 연동 (3단계)
- 고유명사 사전, 코퍼스 누적 (3단계 이후)
- CLI 인터페이스 (불필요 시 추가)
- 슬래시 커맨드로 허용 ID 관리 (2단계)

---

## 2. 아키텍처

### 모듈 간 호출 관계

```
interfaces/telegram/  <-- 사용자 인터페이스 (교체 가능)
         |
         v
    cheroki.core  <-- 순수 함수. Deepgram 호출 + 포맷팅.
         |
         v
    cheroki.storage  <-- 선택적. 저장/조회.
         |
         v
    (SQLite 파일 + 파일시스템)
```

core는 어떤 인터페이스나 저장소와도 무관하게 단독 호출 가능해야 함.

---

## 3. 핵심 API

### Python 라이브러리

```python
from cheroki import transcribe_audio

result = await transcribe_audio("interview.m4a")
print(result.text)

result.utterances      # list[Utterance]
result.duration_sec    # float
result.speaker_count   # int

result.to_srt()        # str
result.to_markdown()   # str
result.to_txt()        # str
result.to_dict()       # dict

from cheroki.storage import SQLiteStore
store = SQLiteStore("siltare.db")
record_id = store.save(result, metadata={...})
```

### Telegram 봇

```bash
python -m cheroki.interfaces.telegram
```

---

## 4. 디렉토리 구조

```
cheroki/
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
├── docker-compose.yml
├── src/cheroki/
│   ├── __init__.py              # 공개 API
│   ├── config.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── types.py
│   │   ├── result.py
│   │   ├── exporter.py
│   │   ├── transcribe.py
│   │   └── transcribers/
│   │       ├── base.py
│   │       └── deepgram.py
│   ├── storage/
│   │   ├── base.py
│   │   ├── sqlite_store.py
│   │   └── fs_store.py
│   └── interfaces/
│       └── telegram/
│           ├── __main__.py
│           ├── bot.py
│           ├── handlers.py
│           └── formatters.py
├── tests/
├── data/                        # gitignore
│   ├── uploads/
│   ├── exports/
│   └── siltare.db
└── docs/
```

---

## 5. 핵심 데이터 타입

### Utterance

```python
@dataclass
class Utterance:
    speaker: int
    start: float
    end: float
    text: str
    confidence: float
```

### TranscriptionResult

- `utterances: list[Utterance]`
- `metadata: TranscriptionMetadata`
- `raw_response: dict` (Deepgram 원본)
- `to_srt() / to_markdown() / to_txt() / to_dict()`

### Transcriber Protocol

```python
class Transcriber(Protocol):
    async def transcribe(self, audio_path: Path) -> TranscriptionResult: ...
```

### Store Protocol

```python
class Store(Protocol):
    def save(self, result, metadata: dict) -> str: ...
    def get(self, record_id: str) -> dict | None: ...
    def list_recent(self, limit: int = 5) -> list[dict]: ...
```

---

## 6. 사용자 시나리오

```
[사용자] 오디오 전송 (캡션: "제목/메모")
[봇]    받았습니다. ID: ab7f3c · 처리 중 (예상 3~5분)
[봇]    완료. 1시간 52분, 화자 2명
         미리보기:
         [S0 00:00:15] 오늘은...
         [S1 00:00:42] 아, 그래...
[봇]    📎 ab7f3c.srt / .md / .txt
```

### 명령어

- (오디오 전송) - 자동 녹취
- `/last` - 최근 5건
- `/get <id>` - 재전송
- `/status <id>` - 상태
- `/help` - 사용법
- `/start` - 환영

---

## 7. 기술 스택

- Python 3.11+
- aiogram v3
- httpx
- python-dotenv
- 표준 logging
- Deepgram Nova-2 (+ diarize)
- Docker Compose (Local Bot API Server)
- SQLite
- uv 권장

---

## 8. SQLite 스키마

```sql
CREATE TABLE transcripts (
    id TEXT PRIMARY KEY,               -- 6자리 base32
    tg_user_id INTEGER,
    tg_username TEXT,
    tg_chat_id INTEGER,
    tg_message_id INTEGER,
    file_name TEXT,
    file_size_bytes INTEGER,
    caption TEXT,
    session_title TEXT,
    status TEXT,                       -- pending | processing | completed | failed
    error TEXT,
    duration_sec REAL,
    speaker_count INTEGER,
    language TEXT,
    model TEXT,
    audio_path TEXT,
    srt_path TEXT,
    md_path TEXT,
    txt_path TEXT,
    raw_json_path TEXT,
    transcript_text TEXT,
    created_at TEXT,
    completed_at TEXT
);
CREATE INDEX idx_tg_user ON transcripts(tg_user_id);
CREATE INDEX idx_status ON transcripts(status);
CREATE INDEX idx_created ON transcripts(created_at DESC);
```

---

## 9. 환경변수

```bash
BOT_TOKEN=...
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
LOCAL_API_URL=http://localhost:8081
DEEPGRAM_API_KEY=...
DEEPGRAM_MODEL=nova-2
ALLOWED_USER_IDS=123,456
DATA_DIR=./data
DB_PATH=./data/siltare.db
LOG_LEVEL=INFO
```

---

## 10. 결정 사항

- short ID: **6자리 base32**
- 원본 보관: 영구
- 재시도: 수동
- 동시 처리: asyncio 자연 병렬
- 레포: 공개 (data/ gitignore)
- em-dash 금지

---

## 11. 로드맵

**1단계 MVP** (이 기획안) — 녹취 + SRT/MD/TXT + Telegram 봇
**2단계** — 화자 이름 치환, 캡션 파싱, AI 교정 루프, 허용 ID 슬래시 커맨드
**3단계** — 실타래 본체 Graphiti 연동, vault 싱크, PostgreSQL 이관
**4단계** — 하회 어르신 아카이브, 구술사 전집, 파인튜닝 데이터셋 공개
