# Cheroki (채로키)

> 採錄 — 구술을 채집하고 기록한다.

음성 전사 파이프라인. 녹음 파일을 넣으면 정확한 텍스트가 나온다.

Whisper로 전사하고, AI가 의심 구간을 잡아내고, 사람이 교정하면 학습한다.
텔레그램으로 녹음 보내면 전사 → SRT/MD 생성 → 교정까지 한 번에.

## 왜 만들었나

음성 녹음을 텍스트로 바꾸는 건 Whisper가 잘 한다. 하지만 고유명사, 전문 용어, 사투리가 나오면 틀린다. 그래서:

1. Whisper가 1차 전사를 하고
2. Claude가 의심 구간을 잡아서 질문하고
3. 사람이 고쳐주면 그 패턴을 기억해서 다음번엔 덜 틀린다

이 루프를 반복하면 **나한테 맞춤화된 전사기**가 된다.

## 주요 기능

- **전사**: faster-whisper 로컬 (GPU/CPU) 또는 OpenAI API
- **AI 교정**: Claude Sonnet이 오류 감지 → 텔레그램에서 대화형 교정
- **산출물**: SRT 자막 + Markdown 문서 (메타데이터 포함)
- **자동 학습**: 교정 패턴 누적 → 고유명사 사전 자동 구축
- **텔레그램 봇**: 파일 전송 → 전사 → SRT/MD → vault 싱크 (전부 자동)
- **웹 UI**: 파일 업로드, 전사 결과 조회, 산출물 다운로드
- **코퍼스**: 교정 쌍 누적 → JSONL/CSV/HuggingFace 내보내기

## 파이프라인

```
음성 파일 (텔레그램 / 웹 / 로컬 폴더)
  → 원본 보관 (절대 삭제 안 함)
  → Whisper 전사 (타임스탬프 포함)
  → SRT + MD 자동 생성
  → Hahnness vault 싱크
  → /correct → AI 교정 대화
  → 최종본 + 산출물 재생성
  → 교정 쌍 코퍼스 + 사전 학습
```

## 설치

```bash
git clone https://github.com/hahnryu/cheroki.git
cd cheroki
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config.yaml.example config.yaml
# config.yaml 수정
```

## 텔레그램 봇 (주요 인터페이스)

```bash
cheroki bot
```

### 명령어

| 명령어 | 기능 |
|--------|------|
| 음성 파일 전송 | 자동 전사 → SRT/MD → vault |
| `/correct` | AI 교정 시작 (대화형) |
| `/done` | 교정 종료 + 최종본 생성 |
| `/show` | 최근 전사 결과 보기 |
| `/list` | 전사 파일 목록 |
| `/export` | SRT + MD 재생성 |
| `/vault` | Hahnness vault 싱크 |
| `/learn` | 교정 패턴 학습 + 사전 업데이트 |
| `/dataset` | 코퍼스 내보내기 (JSONL) |
| `/status` | 시스템 상태 |
| `/help` | 매뉴얼 |

### 교정 플로우

```
/correct
  → AI: "다음을 확인해주세요:
         1. [00:01] "네르핍은" → "네트워크는"?
         2. [00:11] "컴퓨티션" → "컴페티션"?"
  → 자유 답변: "1은 무시해, 2 competition"
  → AI가 해석 + 남은 거 재질문
  → /done → 최종본 + SRT/MD + vault + 코퍼스 + 학습
```

## CLI

```bash
cheroki transcribe recording.mp3    # 전사
cheroki review <file_id>            # 의심 구간 검토
cheroki correct <file_id> corr.json # 교정 적용
cheroki export <file_id>            # SRT + MD 내보내기
cheroki learn                       # 패턴 학습 + 사전
cheroki vault-sync <file_id>        # vault 싱크
cheroki dataset --format jsonl      # 코퍼스 내보내기
cheroki serve --port 8000           # 웹 서버
cheroki watch                       # 폴더 감시
```

## 설정

`config.yaml.example` → `config.yaml`

```yaml
whisper:
  mode: "local"          # "local" (faster-whisper) 또는 "api" (OpenAI)
  model: "medium"        # tiny, base, small, medium, large-v3
  language: "ko"
  device: "cpu"          # cpu 또는 cuda

telegram:
  bot_token: "YOUR_TOKEN"
  allowed_users: []      # 비어있으면 모두 허용

claude_api:
  api_key: ""            # AI 교정용 (Anthropic)

# openai:
#   api_key: ""          # whisper.mode: "api" 일 때
```

## 프로젝트 구조

```
src/cheroki/
├── transcriber.py     # Whisper 전사 (로컬/API)
├── pipeline.py        # 전사 파이프라인
├── storage.py         # 원본 파일 관리
├── ai_reviewer.py     # Claude AI 교정 제안
├── corrector.py       # 교정 반영
├── exporter.py        # SRT, MD 생성
├── learner.py         # 패턴 학습, 사전, vault
├── telegram_bot.py    # 텔레그램 봇
├── web.py             # FastAPI 웹 서버
├── dataset.py         # 코퍼스 패키징/내보내기
├── dictionary.py      # 고유명사 사전
├── reviewer.py        # 의심 구간 추출 (규칙 기반)
├── diarizer.py        # 화자 분리 (pyannote)
├── siltarae.py        # Siltarae 연동
└── ...
src/tests/             # 153개+ 테스트
```

아키텍처 상세: [ARCHITECTURE.md](ARCHITECTURE.md)
개발 저널: [JOURNAL.md](JOURNAL.md)

## 프라이버시

- 로컬 모드: **모든 처리가 로컬**. 음성 원본 외부 전송 없음.
- API 모드: 음성이 OpenAI 서버로 전송됨 (config에서 전환)
- AI 교정: 텍스트만 Claude에 전송 (음성 아님)
- `data/` 디렉토리는 git에 포함되지 않음

## 기술 스택

- Python 3.11+
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — 로컬 전사
- [Claude API](https://docs.anthropic.com/) — AI 교정
- [python-telegram-bot](https://python-telegram-bot.org/) — 텔레그램
- [FastAPI](https://fastapi.tiangolo.com/) — 웹 서버

## 라이선스

MIT
