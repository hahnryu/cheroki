# Cheroki (채로키)

> 採錄 — 구술을 채집하고 기록한다.

로컬에서 돌아가는 음성 전사 파이프라인. 녹음 파일을 넣으면 정확한 텍스트가 나온다.

Whisper를 로컬에서 돌리고, 의심 구간을 잡아내고, 사람이 교정하면 그걸 학습한다. 교정할수록 똑똑해지는 전사기.

## 왜 만들었나

음성 녹음을 텍스트로 바꾸는 건 Whisper가 잘 한다. 하지만 고유명사, 전문 용어, 사투리가 나오면 틀린다. 그래서:

1. Whisper가 1차 전사를 하고
2. 신뢰도가 낮은 구간을 자동으로 잡아서 "이거 맞아?" 하고 물어보고
3. 사람이 고쳐주면 그 패턴을 기억해서 다음번엔 덜 틀린다

이 루프를 반복하면 **나한테 맞춤화된 전사기**가 된다.

## 주요 기능

- **로컬 전사**: faster-whisper 기반, GPU/CPU 모두 지원
- **교정 루프**: 의심 구간 자동 추출 → 질문 생성 → 교정 반영
- **산출물**: SRT 자막 + Markdown 문서 (메타데이터, 화자 분리 포함)
- **자동 학습**: 교정 패턴 누적 → 고유명사 사전 자동 구축
- **텔레그램 봇**: 음성 파일 보내면 자동 전사 후 결과 회신
- **웹 UI**: 파일 업로드, 전사 결과 조회, 산출물 다운로드
- **코퍼스 관리**: 교정 쌍 누적 → JSONL/CSV/HuggingFace 형식 내보내기

## 파이프라인

```
음성 파일 (텔레그램 / 웹 / 로컬 폴더)
  → 원본 보관 (절대 삭제 안 함)
  → Whisper 로컬 전사 (타임스탬프 포함)
  → 의심 구간 자동 추출 → 질문 목록 생성
  → 사용자 교정 → 패턴 학습
  → 최종 녹취록 (SRT + MD)
  → 교정 쌍 코퍼스로 누적
```

## 설치

```bash
# 클론
git clone https://github.com/hahnryu/cheroki.git
cd cheroki

# 가상환경
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 설치
pip install -e ".[dev]"

# 설정
cp config.yaml.example config.yaml
# config.yaml을 환경에 맞게 수정
```

## 사용법

### CLI

```bash
# 음성 파일 전사
cheroki transcribe recording.mp3

# 의심 구간 검토
cheroki review <file_id>

# 교정 적용
cheroki correct <file_id> corrections.json

# SRT + MD 내보내기
cheroki export <file_id>

# 교정 패턴 학습 + 사전 업데이트
cheroki learn

# 코퍼스 데이터셋 내보내기
cheroki dataset --format jsonl
cheroki dataset --format csv
cheroki dataset --format huggingface
```

### 텔레그램 봇

```bash
# config.yaml에 bot_token 설정 후
cheroki bot
```

봇에 음성 파일을 보내면 자동으로 전사하여 결과를 회신한다.

### 웹 UI

```bash
cheroki serve --port 8000
```

`http://localhost:8000`에서 파일 업로드, 전사 결과 조회, 산출물 다운로드.

### 폴더 감시

```bash
# originals/ 폴더에 파일이 들어오면 자동 전사
cheroki watch
```

## 설정

`config.yaml.example`을 `config.yaml`로 복사하여 사용.

```yaml
whisper:
  model: "medium"      # tiny, base, small, medium, large-v3
  language: "ko"
  device: "cpu"        # cpu 또는 cuda
  compute_type: "int8" # int8, float16, float32

telegram:
  bot_token: "YOUR_BOT_TOKEN"
  allowed_users: []    # 비어있으면 모두 허용
```

## 프로젝트 구조

```
cheroki/
├── src/cheroki/
│   ├── transcriber.py     # Whisper 전사 엔진
│   ├── storage.py         # 원본 파일 저장/관리
│   ├── reviewer.py        # 의심 구간 추출, 질문 생성
│   ├── corrector.py       # 교정 반영
│   ├── exporter.py        # SRT, MD 산출물 생성
│   ├── learner.py         # 패턴 학습, 사전 자동 구축, vault 연동
│   ├── telegram_bot.py    # 텔레그램 봇
│   ├── web.py             # FastAPI 웹 서버
│   ├── dataset.py         # 코퍼스 패키징, 내보내기
│   └── ...
├── config.yaml.example
├── pyproject.toml
└── src/tests/             # 151개 테스트
```

## 프라이버시

- **모든 처리가 로컬에서 실행됨**. Whisper 모델은 로컬 실행.
- 음성 원본은 외부로 전송되지 않음
- 데이터는 로컬 디스크에만 존재
- `data/` 디렉토리는 git에 포함되지 않음

## 기술 스택

- Python 3.11+
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — 로컬 음성 전사
- [FastAPI](https://fastapi.tiangolo.com/) — 웹 서버
- [python-telegram-bot](https://python-telegram-bot.org/) — 텔레그램 연동
- Click — CLI
- structlog — 구조화 로깅

## 라이선스

MIT
