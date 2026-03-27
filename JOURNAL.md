# Cheroki 개발 저널

## 2026-03-27 — Phase 3+4+5 완성 + 텔레그램 봇 실전 테스트

### 세션 요약

하루 만에 Phase 3(지능화), Phase 4(인터페이스), Phase 5(코퍼스)를 모두 구현하고,
실제 녹음 파일(아버지 류중하 인터뷰, 혁재 클래리티법안 대화)로 실전 테스트를 진행함.
OpenAI Whisper API의 호환성 문제를 겪고 로컬 Whisper로 전환.
텔레그램 봇을 전면 재설계하여 전사/교정/산출물/학습을 모두 /커맨드로 통합.

### 진행 순서

#### 1. Phase 4 — 인터페이스 (3a156c0 ~ adbcc28)
- **텔레그램 봇** (`telegram_bot.py`): python-telegram-bot, /start /help /status, 음성 파일 수신 → 전사 파이프라인 연동
- **FastAPI 웹 서버** (`web.py` + `templates/index.html`): 파일 업로드, 전사 조회, SRT/MD 다운로드
- **Siltarae 연동** (`siltarae.py`): Fragment 변환, HTTP 전송, 로컬 fallback

#### 2. Phase 3 — 지능화 (620594c)
- **learner.py**: 교정 코퍼스에서 고유명사 자동 추출, 교정 패턴 학습, 자동 교정 제안
- **vault 연동**: 최종 MD를 Hahnness vault 폴더로 복사
- CLI: `cheroki learn`, `cheroki vault-sync`

#### 3. Phase 5 — 코퍼스 (3ad663d)
- **dataset.py**: 코퍼스 패키징, 메타데이터 태깅 (화자, 방언, 주제), JSONL/CSV/HuggingFace 내보내기
- CLI: `cheroki dataset`, `cheroki package`

#### 4. GitHub 공개 (9b06378 ~ 525ac36)
- git history에서 config.yaml (토큰 포함) 완전 제거 (`git-filter-repo`)
- config.yaml → config.yaml.example 분리
- .gitignore 보강, MIT 라이선스, 공개용 README
- https://github.com/hahnryu/cheroki

#### 5. Whisper 로컬/API 모드 전환 (7329a7a)
- config.yaml에서 `whisper.mode: "local" | "api"` 한 줄로 전환
- `LocalTranscriber` (faster-whisper) / `APITranscriber` (OpenAI)
- `create_transcriber()` 팩토리 함수

#### 6. OpenAI API 호환성 문제 (206fd24 ~ 9e80a1f)
- 25MB 파일 제한 → ffmpeg 자동 분할 (10분 단위 mp3 64kbps)
- 텔레그램 음성(.ogg opus) → mp3 자동 변환
- `verbose_json` 전면 미지원 발견 (OpenAI가 whisper-1을 gpt-4o-transcribe로 라우팅)
- `gpt-4o-transcribe-diarize` 시도 → 화자 정보 미포함 확인
- **결론: 로컬 Whisper(faster-whisper)가 세그먼트/타임스탬프에 가장 안정적**

#### 7. 실전 테스트
- **아버지 류중하 인터뷰** (30분, 12.5MB m4a): 529개 세그먼트 정상 전사 (API)
- **혁재 클래리티법안 대화** (2분 30초, 3.7MB m4a): 29개 세그먼트 정상 전사 (로컬)
- 고유명사 오류 확인: 유시현→류시현, 여현미→류현미, 컴퓨티션→컴페티션 등

#### 8. AI 교정 플로우 (6773429 ~ 1715c25)
- Claude Sonnet API 연동 (`ai_reviewer.py`): 전사 결과 분석 → 교정 제안
- 초기: 하나씩 질문 방식 → 일괄 질문 방식 → 최종: **대화형 교정**
- 자연어 응답 처리: "맞아"=수락, "무시"=건너뛰기, "나중에"=보류

#### 9. 텔레그램 봇 전면 재설계 (1715c25)
- 전사와 교정을 완전히 분리
- 파일 전송 → 전사 + SRT/MD + vault (전부 자동)
- /correct → Sonnet 대화형 교정 → 최종본 + 재생성 + vault + 코퍼스 + 학습
- 모든 CLI 기능을 /커맨드로 매핑

### 발견한 문제 + 결정

| 문제 | 결정 |
|------|------|
| OpenAI verbose_json 미지원 | 로컬 Whisper 사용 (타임스탬프 안정) |
| OpenAI diarize 모델 화자 정보 없음 | 화자 분리 보류 (추후 pyannote 또는 API) |
| GPU 없음 (WSL CPU) | medium 모델 + CPU, 10-20분/30분 파일 |
| 교정 UX: 하나씩 질문 느림 | 대화형으로 전환 (Sonnet이 자유 답변 해석) |

### 남은 과제

- 화자 분리 (diarization) — GPU 서버 확보 후 pyannote 또는 API
- 교정 UX 실전 검증 — Sonnet 대화형 교정 품질 확인
- 웹 UI 고도화 — 현재 기본 수준
- config.yaml 내 토큰 관리 자동화
