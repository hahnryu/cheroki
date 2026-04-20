# Cheroki · 採錄

> 구술을 채집하고 기록한다.
>
> 한국어 음성을 화자분리된 텍스트로 변환하는 Python 모듈 + Telegram 봇 + CLI.
> 실타래(Siltare) 생태계의 STT 모듈이자 스탠드얼론 라이브러리.

## 무엇을 하는가

1. 오디오/비디오 파일을 받는다 (Telegram 봇, CLI, Python API 세 가지 진입점).
2. Deepgram Nova-2로 한국어 전사 + 화자분리 + 타임스탬프.
3. SRT / Markdown / TXT / Deepgram raw JSON 네 가지 산출.
4. `DATA_DIR/YYMMDD/<slug>_raw.<ext>` 구조로 저장 (self-describing).
5. SQLite에 메타데이터.

cheroki는 **1차 채록 단계**만 책임진다. 이후 교정·화자 이름지정·요약·vault 싱크는 별도 도구가 cheroki의 폴더 위에서 작동한다.

## 저장 규약

```
DATA_DIR/
├── 260420/                          (녹음 날짜, YYMMDD)
│   ├── abeonim_morning_walk_raw.m4a   원본 오디오
│   ├── abeonim_morning_walk_raw.srt   자막
│   ├── abeonim_morning_walk_raw.md    Markdown (YAML frontmatter + 본문)
│   ├── abeonim_morning_walk_raw.txt   플레인 텍스트
│   └── abeonim_morning_walk_raw.json  Deepgram 원본 응답
└── siltare.db
```

`<slug>`는 캡션 또는 원본 파일명을 romanize한 ASCII 슬러그. 없으면 short ID(6자리).

## 설치

```bash
git clone <repo> cheroki && cd cheroki
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

cp .env.example .env
# .env 에 Deepgram API 키, Telegram 봇 토큰, 허용 user ID 입력
```

상세 설정은 [docs/SETUP.md](docs/SETUP.md).

## 라이브러리로 쓰기

```python
import asyncio
from cheroki import transcribe_audio

async def main():
    result = await transcribe_audio("interview.m4a")
    print(result.text)              # 화자 + 타임스탬프 포함
    print(result.duration_sec)      # 1234.5
    print(result.speaker_count)     # 2

    with open("out.srt", "w", encoding="utf-8") as f:
        f.write(result.to_srt())

asyncio.run(main())
```

SQLite + 파일시스템 저장까지 한 번에:
```python
from cheroki.storage import SQLiteStore, FileStore
from cheroki.naming import build_slug
from datetime import date

db = SQLiteStore("siltare.db")
fs = FileStore("./data")

rec_id = db.save(result, {
    "file_name": "interview.m4a",
    "session_title": "인터뷰",
    "recording_date": date(2026, 4, 20),
})
slug = build_slug(caption="인터뷰", original_filename="interview.m4a", record_id=rec_id)
fs.write_exports(date(2026, 4, 20), slug, result, frontmatter_extra={
    "title": "인터뷰", "record_id": rec_id, "source": "library",
})
```

## CLI로 쓰기

```bash
# 파일 하나 녹취
cheroki transcribe recording.m4a --caption "아버님 morning walk 260420 하회 부용대"
# → data/260420/abeonim_morning_walk_hahoe_buyongdae_raw.{m4a,srt,md,txt,json}

# 옵션
cheroki transcribe rec.m4a \
  --date 260420 \
  --title "구술사 세션" \
  --place "하회 부용대" \
  --out /custom/path

# stdout만 (저장 없음)
cheroki transcribe rec.m4a --no-save

# 레코드 조회
cheroki info ab7f3c

# Telegram 봇 기동
cheroki bot
```

## Telegram 봇으로 쓰기

```bash
# 1. Local Bot API 서버 (2GB 대응 Docker)
docker compose up -d

# 2. 봇 기동
cheroki bot
```

Telegram에서 @cheroki_siltarebot에게 오디오 전송 → 녹취가 SRT/MD/TXT로 회신.

**캡션 규약 (자유형식)**: 날짜를 넣으면 자동 추출해 폴더로. 예: `"260420 하회 morning walk"`, `"아버님 구술사 2026-04-20"`.

### 봇 명령어

- `(오디오 전송)` — 자동 녹취
- `/last` — 최근 녹취 5건
- `/get <id>` — 특정 건 파일 재전송
- `/status <id>` — 처리 상태 조회
- `/help` — 도움말

배포 방법은 [docs/DEPLOY.md](docs/DEPLOY.md).

## 디렉토리 구조

```
cheroki/
├── src/cheroki/
│   ├── core/              순수 라이브러리 (Deepgram, SRT/MD/TXT)
│   ├── storage/           SQLite + FileStore (YYMMDD/<slug>_raw.* 레이아웃)
│   ├── interfaces/
│   │   ├── cli.py         cheroki 명령어
│   │   └── telegram/      aiogram v3 봇
│   ├── naming.py          캡션 파싱, romanize, 슬러그
│   ├── migrate.py         구 레이아웃 → 신 레이아웃
│   └── config.py          .env 로딩
├── tests/                 pytest
├── docs/                  PLAN_v3, SETUP, DEPLOY, CONCEPTS, JOURNAL
├── data/                  gitignore
├── docker-compose.yml     Local Bot API 서버만
└── CLAUDE.md              프로젝트 철학 + 작업 규칙
```

## 개발

```bash
pytest                        # 테스트
ruff check src/ tests/        # 린트
ruff check --fix src/ tests/  # 자동 수정

cheroki migrate --dry-run     # 구→신 레이아웃 이주 계획 미리보기
cheroki migrate               # 실제 이주
```

## 로드맵

- **Phase 1 (완료)**: MVP — 전사 + SRT/MD/TXT + Telegram 봇 + CLI + 네이밍 규약
- **Phase 1.5**: Local Bot API 2GB 모드 안정화
- **Phase 2**: 화자 이름 치환, AI 교정 루프, 캡션 파싱 강화
- **Phase 3**: 실타래 본체 Graphiti 연동, vault 싱크
- **Phase 4**: 구술사 아카이브, 파인튜닝 데이터셋 공개

상세는 [docs/PLAN_v3.md](docs/PLAN_v3.md). 작업 맥락은 [docs/JOURNAL.md](docs/JOURNAL.md).

## 프라이버시

- `data/` 폴더는 .gitignore. 오디오/전사는 로컬에만.
- Deepgram에는 음성 바이트가 전송된다 (전사 목적). 텍스트 결과는 즉시 로컬로.

## 라이선스

MIT.
