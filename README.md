# Cheroki · 採錄

> 구술을 채집하고 기록한다.
>
> 한국어 음성을 화자분리된 텍스트로 변환하는 Python 모듈 + Telegram 봇.
> 실타래(Siltare) 생태계의 STT 모듈이자 스탠드얼론 라이브러리.

## 무엇을 하는가

1. 오디오/비디오 파일을 받는다 (Telegram 봇 또는 Python API).
2. Deepgram Nova-2로 한국어 전사 + 화자분리 + 타임스탬프.
3. SRT 자막 + Markdown + TXT 세 가지 형식으로 산출.
4. SQLite에 메타데이터, 파일시스템에 원본/산출물 저장.

Telegram 봇(@cheroki_siltarebot)으로 쓰는 것이 기본이지만, core 모듈은 순수 라이브러리로 다른 프로젝트에서 한 줄로 호출 가능하다.

## 설치

```bash
git clone <repo> cheroki && cd cheroki
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

cp .env.example .env
# .env 파일에 Deepgram API 키, Telegram 봇 토큰, 허용 user ID 입력
```

상세 설정은 [docs/SETUP.md](docs/SETUP.md) 참고.

## 라이브러리로 쓰기

```python
import asyncio
from cheroki import transcribe_audio

async def main():
    result = await transcribe_audio("interview.m4a")
    print(result.text)              # 화자 + 타임스탬프 포함 포맷
    print(result.duration_sec)      # 1234.5
    print(result.speaker_count)     # 2

    with open("out.srt", "w", encoding="utf-8") as f:
        f.write(result.to_srt())
    with open("out.md", "w", encoding="utf-8") as f:
        f.write(result.to_markdown(title="인터뷰"))

asyncio.run(main())
```

저장까지 한 번에:

```python
from cheroki.storage import SQLiteStore, FileStore

db = SQLiteStore("siltare.db")
fs = FileStore("./data")

rec_id = db.save(result, {"title": "인터뷰", "file_name": "interview.m4a"})
fs.write_exports(rec_id, result, title="인터뷰")
```

## Telegram 봇으로 쓰기

```bash
# 1. Local Bot API 서버 (2GB 파일 수신용 Docker 컨테이너)
docker compose up -d

# 2. 봇 실행
python -m cheroki.interfaces.telegram
```

Telegram에서 봇(@cheroki_siltarebot)에게 오디오를 보내면 녹취가 SRT/MD/TXT로 회신된다.

### 명령어

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
│   ├── core/              # 순수 라이브러리: 전사, 포맷팅
│   ├── storage/           # SQLite + 파일시스템
│   ├── interfaces/
│   │   └── telegram/      # aiogram v3 봇
│   └── config.py
├── tests/                 # pytest
├── docs/                  # PLAN_v3, SETUP, DEPLOY, CONCEPTS
├── data/                  # gitignore (오디오, 녹취, DB)
└── docker-compose.yml     # Local Bot API 서버만
```

## 개발

```bash
# 테스트
pytest

# 린트
ruff check .
```

## 범위

**MVP (현재)**: Telegram 봇 + Deepgram Nova-2 + SRT/MD/TXT + SQLite.
**2단계**: 화자 이름 치환, AI 교정 루프, 캡션 파싱.
**3단계**: 실타래 본체 Graphiti 연동, vault 싱크.

상세 로드맵은 [docs/PLAN_v3.md](docs/PLAN_v3.md) 참고.

## 프라이버시

- `data/` 폴더는 .gitignore 대상. 오디오/전사 데이터는 로컬에만 저장.
- Deepgram에는 음성 바이트를 전송한다 (전사 목적). 텍스트 결과는 즉시 로컬로 회수.

## 관련

- [실타래(Siltare)](https://github.com/...) — 본체
- 이전 cheroki (deprecated): `d:/projects/cheroki_legacy/` — 범위 과대 + 로컬 Whisper 의존으로 실패. 참고용 보존.

## 라이선스

MIT.
