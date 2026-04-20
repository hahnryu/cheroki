# Cheroki — CLAUDE.md

음성 전사 파이프라인. 실타래(Siltare) 생태계의 STT 모듈. 스탠드얼론 라이브러리로도 작동.

## 철학

**cheroki = raw 채록만.** 교정, 화자 이름지정, 요약, 검색은 별도 모듈이 나중에 이 위에 얹힌다. cheroki의 책임 범위:

1. 오디오 수신 (Telegram 봇 / Python 라이브러리 / CLI)
2. Deepgram 전사 + 화자분리 + 타임스탬프
3. SRT / Markdown / TXT / raw.json 네 가지 형식 생성
4. `DATA_DIR/YYMMDD/<slug>_raw.<ext>` 레이아웃으로 저장
5. SQLite에 메타데이터 + 경로 인덱싱

이후의 교정·이름지정·vault 싱크·Graphiti 연동 등은 cheroki의 폴더 구조를 입력으로 받는 별도 도구들이 맡는다. cheroki는 그 하류 도구들이 작업하기 좋은 **깔끔하고 안정적인 원자료 저장소**를 만든다.

## 저장 규약 (중요)

**이 규약은 하류 도구들이 의존한다. 함부로 바꾸지 않는다.**

```
DATA_DIR/
├── YYMMDD/                                  (녹음 날짜 기준 폴더)
│   ├── <slug>_raw.m4a (또는 .ogg, .mp3 등)   원본 오디오
│   ├── <slug>_raw.srt                         타임스탬프 자막
│   ├── <slug>_raw.md                          Markdown (YAML frontmatter + 본문)
│   ├── <slug>_raw.txt                         플레인 텍스트
│   └── <slug>_raw.json                        Deepgram 원본 응답
└── siltare.db                                 SQLite 메타데이터
```

- `YYMMDD`: 녹음 날짜(캡션에서 추출 > Telegram 수신 시각 > 파일 mtime > today).
- `<slug>`: 캡션/원본 파일명을 romanize한 ASCII 슬러그. 없으면 short ID(6자리 Crockford base32).
- `_raw` 접미어: 1차 채록 산출물임을 표시. 교정본은 `_edited`, 이름지정본은 `_named` 등 다른 접미어 사용.

## 코드 규칙

1. **Python 3.11+**, async/await 통일, 타입 힌트 필수
2. **aiogram v3** (python-telegram-bot 금지), httpx, python-dotenv, unidecode
3. **표준 logging** (structlog 안 씀). 모듈마다 `logger = logging.getLogger(__name__)`
4. **em-dash(—) 금지**. 콤마, 콜론, 괄호, 줄바꿈으로 대체
5. **설정은 .env로**. `config.yaml` 금지 (레거시 유물). 로딩은 `cheroki.config.load_config()`
6. **하드코딩 경로 금지**. 모든 경로는 `DATA_DIR`·slug·date 조합으로 계산
7. **에러 시 음성 원본이 손상/삭제되는 일 절대 없어야** 한다. 실패는 SQLite에 `status='failed'`로만 마킹
8. **git commit은 기능 단위.** 메시지 한국어 가능

## 모듈 구조

```
src/cheroki/
├── __init__.py              공개 API (transcribe_audio, TranscriptionResult, Utterance)
├── config.py                .env 로딩
├── naming.py                캡션 파싱, romanize, 슬러그 생성, 세션 폴더명
├── migrate.py               레이아웃 마이그레이션 (구버전 → 신버전)
│
├── core/                    순수 라이브러리 (인터페이스/저장 독립)
│   ├── types.py             Utterance, TranscriptionMetadata
│   ├── result.py            TranscriptionResult (+ to_srt/md/txt/dict)
│   ├── exporter.py          SRT/MD/TXT 렌더러
│   ├── transcribe.py        transcribe_audio() 진입점
│   └── transcribers/        전사 엔진 (현재 Deepgram)
│
├── storage/                 저장 계층
│   ├── base.py              Store Protocol
│   ├── ids.py               6자리 Crockford base32 short ID
│   ├── sqlite_store.py      SQLiteStore
│   └── fs_store.py          FileStore (새 레이아웃)
│
└── interfaces/              인터페이스 (봇·CLI)
    ├── cli.py               `cheroki transcribe|bot|migrate|info`
    └── telegram/            aiogram v3 봇
```

core는 어떤 인터페이스/저장소 없이도 독립 호출 가능해야 한다. 실타래 본체가 `from cheroki import transcribe_audio` 한 줄로 쓸 수 있어야 함.

## 개발 워크플로우

```bash
# 의존성
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 테스트 (모든 PR에서 통과해야 함)
uv run pytest -q

# 린트
uv run ruff check src/ tests/
uv run ruff check --fix src/ tests/   # 자동 수정

# CLI 실행
uv run cheroki transcribe path/to/audio.m4a --caption "아버님 walk 260420 하회"

# 봇 기동 (.env 필요)
uv run cheroki bot
# 또는
uv run python -m cheroki.interfaces.telegram

# 마이그레이션 (구 레이아웃 → 신)
uv run cheroki migrate --dry-run   # 계획만
uv run cheroki migrate              # 실제 이동
```

## 사용자 확인 필요 지점

자율적으로 진행하되, 아래는 반드시 멈추고 묻는다:

- 외부 API 키/토큰 필요 시
- 저장 규약 변경 (하류 도구와 인터페이스 깨짐)
- SQLite 스키마 비호환 변경 (마이그레이션 경로 고민 필요)
- `data/` 내부 파일 삭제/덮어쓰기
- 프라이버시에 영향을 주는 결정

## 연동

- **Deepgram API**: Nova-2 + diarize. 키는 .env의 `DEEPGRAM_API_KEY`
- **Telegram**: @cheroki_siltarebot. Local Bot API 서버(Docker)로 2GB 파일 수신 가능
- **Hahnness vault**: 별도의 sink 도구가 `DATA_DIR/YYMMDD/*.md`를 vault로 복사 (cheroki 자체는 vault를 모른다)
- **실타래 본체**: 3단계에서 Graphiti 연동 예정 (cheroki의 _raw.md를 원자료로 투입)

## 프라이버시

- `data/` 폴더는 절대 git에 올리지 않는다
- Deepgram에 음성 원본을 전송한다 (전사 목적). 민감 데이터는 별도 로컬 Whisper fallback 고려 (2단계)
- 모든 레코드는 로컬 디스크에만 존재

## 연관 문서

- [docs/PLAN_v3.md](docs/PLAN_v3.md) — 기획안 v3 (로드맵)
- [docs/JOURNAL.md](docs/JOURNAL.md) — 개발 저널
- [docs/SETUP.md](docs/SETUP.md) — 초기 설정
- [docs/DEPLOY.md](docs/DEPLOY.md) — 배포
- [docs/CONCEPTS.md](docs/CONCEPTS.md) — 배경 지식 (SQLite, Docker, aiogram 등)

## 레거시

이전 cheroki(`/mnt/d/projects/cheroki_legacy/`, 2026-03)는 범위 과대 + 로컬 Whisper 의존으로 실패. 참고용으로만 보존. 코드 재사용 금지 (패턴만 참고).
