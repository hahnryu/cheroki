# Cheroki 아키텍처 문서

## 개요

Cheroki는 음성 파일을 받아 텍스트로 전사하고, AI 교정을 거쳐 최종 문서를 생성하는 파이프라인.
텔레그램 봇이 주요 인터페이스이고, CLI와 웹 UI도 사용 가능.

```
음성 파일
  ↓
[전사] transcriber.py (로컬 Whisper 또는 OpenAI API)
  ↓
[저장] storage.py → originals/
       transcript_store.py → transcripts/
  ↓
[산출물] exporter.py → exports/ (SRT + MD)
         metadata.py (날짜, 장소, 참가자 추출)
  ↓
[vault 싱크] learner.py → Hahnness vault
  ↓
[교정] ai_reviewer.py (Claude Sonnet) → 사용자 대화
       corrector.py → transcripts/{file_id}_final
  ↓
[학습] corpus.py → corpus/ (교정 쌍)
       learner.py → dictionary/ (고유명사), corrections/patterns.json
```

## 모듈 의존 관계

```
telegram_bot.py ──→ pipeline.py ──→ storage.py
      │                   │         transcriber.py
      │                   │         transcript_store.py
      │                   │
      ├──→ ai_reviewer.py (Claude API)
      ├──→ corrector.py
      ├──→ exporter.py ──→ metadata.py
      ├──→ learner.py ──→ dictionary.py
      │                   corpus.py
      ├──→ dataset.py ──→ corpus.py
      └──→ transcript_store.py

web.py ──→ pipeline.py, exporter.py, transcript_store.py, metadata.py
cli.py ──→ 위 모든 모듈 (lazy import)
config.py ──→ (독립, 모든 모듈이 사용)
```

## 모듈별 상세

### config.py
- `load_config(path)` → config.yaml 로드, `~` 경로 확장
- `get_config(path)` → 로드 + 데이터 디렉토리 생성
- 모든 경로는 config.yaml에서 관리. 하드코딩 없음.

### transcriber.py — 전사 엔진
- `LocalTranscriber`: faster-whisper 로컬 실행
  - 모델: tiny/base/small/medium/large-v3
  - CPU/CUDA 지원, compute_type 설정 가능
  - **verbose_json으로 세그먼트+타임스탬프 제공 (안정)**
- `APITranscriber`: OpenAI Whisper API
  - 25MB 초과 시 ffmpeg로 10분 단위 분할
  - 비호환 형식(ogg 등) → mp3 자동 변환
  - **주의: 2026-03 기준 verbose_json 미지원. 세그먼트 없이 텍스트만 반환**
- `create_transcriber(config)`: config.yaml `whisper.mode`에 따라 팩토리 생성
- 데이터 모델: `Segment(start, end, text, confidence)`, `TranscriptionResult`

### storage.py — 원본 파일 관리
- `store_original(source, originals_dir)`: 파일 복사 + SHA-256 해시 검증 + 메타데이터
- file_id 생성 규칙: `{YYYYMMDD_HHMMSS}_{원본파일명}`
- 원본은 **절대 삭제하지 않음**

### transcript_store.py — 전사 결과 저장/로드
- JSON 형식, `{file_id}.transcript.json`
- `save_transcript(result, dir, file_id)` / `load_transcript(path)`

### pipeline.py — 전사 파이프라인
- `run_pipeline(audio_path, config)`: 원본 저장 → 전사 → 결과 저장
- 반환: `{file_id, metadata, transcript_path, result}`

### reviewer.py — 의심 구간 추출 (규칙 기반)
- `extract_suspicious(result, dictionary, min_confidence)`: 낮은 신뢰도, 미등록 고유명사 감지
- `generate_questions(result, suspicious)`: 질문 목록 생성 (타임스탬프 + 전후 맥락)

### ai_reviewer.py — AI 교정 제안 (Claude API)
- `suggest_corrections_ai(segments, api_key)`: Claude Sonnet에 전사 결과 전송 → 교정 제안 반환
- 프롬프트: 잘못 들은 단어, 고유명사 오류, 문맥 오류 감지
- 응답: JSON 배열 `[{index, original, suggested, reason}]`

### corrector.py — 교정 반영
- `Correction(segment_index, original_text, corrected_text)`
- `apply_corrections(result, corrections)`: 원본 변경 없이 새 TranscriptionResult 반환
- `save_corrections(correction_set, dir)`: 교정 이력 JSON 저장

### exporter.py — 산출물 생성
- `generate_srt(result)` / `save_srt(result, dir, file_id)`: SRT 자막
- `generate_markdown(result, file_id, metadata)` / `save_markdown(...)`: YAML frontmatter + 타임스탬프 MD

### metadata.py — 메타데이터 추출
- `extract_metadata(file_id, source_file, full_text)`: 파일명/텍스트에서 날짜, 장소, 참가자 추출

### dictionary.py — 고유명사 사전
- YAML 파일 기반, 카테고리별 관리
- `Dictionary.load_directory(dir)`: dictionary/*.yaml 로드
- `contains(word)`, `add(word, category)`, `save_file(path)`

### learner.py — 지능화
- `extract_proper_nouns_from_corrections(corpus_dir)`: 교정 코퍼스에서 고유명사 후보 추출
- `auto_update_dictionary(corpus_dir, dictionary, min_frequency)`: 빈도 기준 사전 자동 추가
- `learn_correction_patterns(corpus_dir)`: 반복 교정 패턴 학습
- `suggest_corrections(text, patterns)`: 패턴 기반 자동 교정 제안
- `route_to_vault(md_path, config)`: Hahnness vault로 MD 복사

### corpus.py — 교정 쌍 코퍼스
- `save_corpus_pairs(file_id, corrections, corpus_dir)`: 원본/교정 쌍 저장
- `load_corpus_pairs(path)`, `count_corpus_pairs(dir)`, `list_corpus_files(dir)`

### dataset.py — 데이터셋 내보내기
- `CorpusPackage`: 원본음성+전사+교정을 하나의 패키지로
- `CorpusTag`: 화자 나이, 방언, 주제 등 메타데이터
- `export_jsonl(corpus_dir, output, tags_dir)`: JSON Lines
- `export_csv(...)`: CSV
- `export_huggingface(...)`: HuggingFace datasets 형식

### diarizer.py — 화자 분리
- `diarize(audio_path)`: pyannote-audio 기반 (미설치 시 빈 리스트)
- `assign_speakers(result, speaker_segments)`: 전사 세그먼트에 화자 라벨 부착
- **현재 미사용** — GPU 없어서 실전 사용 불가

### siltarae.py — Siltarae 연동
- `Fragment`: 음성 전사에서 추출된 지식 단위
- `SiltaraeClient.send(result, file_id)`: API 전송 또는 로컬 저장 fallback

### watcher.py — 폴더 감시
- `watch_folder(target, callback)`: watchdog으로 새 음성 파일 감지 → 콜백

### telegram_bot.py — 텔레그램 봇 (주요 인터페이스)
- `CherokiBot(config)`: 봇 초기화
- **자동 파이프라인**: 파일 수신 → 전사 → SRT/MD → vault
- **대화형 교정**: /correct → Sonnet 질문 → 자유 답변 → AI 해석 → 교정 반영 → 재생성
- 명령어: /start /help /status /list /show /correct /done /export /vault /learn /dataset

### web.py — FastAPI 웹 서버
- `create_app(config)`: FastAPI 앱 생성
- 엔드포인트: /, /api/upload, /api/files, /api/transcript/{id}, /api/export/{id}, /api/download/{id}/{fmt}
- Jinja2 템플릿 기반 웹 UI (`templates/index.html`)

### cli.py — CLI 인터페이스
- Click 기반, `cheroki` 명령어
- transcribe, review, correct, export, watch, learn, vault-sync, dataset, package, serve, bot

## 데이터 흐름

```
~/cheroki-data/
├── originals/          ← store_original()
│   ├── {file_id}.mp3   (원본 음성, 절대 삭제 안 함)
│   └── {file_id}.meta.json
├── transcripts/        ← save_transcript()
│   ├── {file_id}.transcript.json        (1차 전사)
│   └── {file_id}_final.transcript.json  (교정 후)
├── corrections/        ← save_corrections()
│   ├── {file_id}.corrections.json
│   └── patterns.json                    (학습된 패턴)
├── corpus/             ← save_corpus_pairs()
│   └── {file_id}.corpus.json
└── exports/            ← save_srt(), save_markdown()
    ├── {file_id}.srt
    ├── {file_id}.md
    └── dataset.jsonl
```

## 설정 구조 (config.yaml)

```yaml
paths:
  originals, transcripts, corrections, corpus, exports
  vault, vault_log  # Hahnness vault

whisper:
  mode: "local" | "api"
  model: "medium"          # 로컬
  language: "ko"
  device: "cpu" | "cuda"   # 로컬

openai:
  api_key: ""              # API 모드

telegram:
  bot_token: ""
  allowed_users: []

claude_api:
  api_key: ""              # AI 교정

siltarae:
  api_url: ""
  api_key: ""
```

## 수정 가이드

### 전사 엔진 변경
- `transcriber.py`의 `LocalTranscriber` 또는 `APITranscriber` 수정
- 새 엔진 추가 시 `create_transcriber()`에 분기 추가
- `TranscriptionResult`와 `Segment` 인터페이스 유지하면 나머지 모듈 영향 없음

### 교정 AI 변경 (Sonnet → 다른 모델)
- `ai_reviewer.py`의 API 호출 부분 수정
- `telegram_bot.py`의 `_process_correction_reply()`에서 Claude API 호출 부분
- 프롬프트는 두 곳: `ai_reviewer.py`(초기 분석), `telegram_bot.py`(대화형 교정)

### 텔레그램 봇 명령어 추가
- `telegram_bot.py`에 `cmd_xxx()` 메서드 추가
- `build_application()`에 `CommandHandler` 등록
- 대화형(여러 턴)이면 `ConversationHandler` 사용

### 산출물 형식 추가
- `exporter.py`에 새 함수 추가 (generate_xxx, save_xxx)
- `telegram_bot.py`의 `_generate_exports()`에서 호출

### 화자 분리 활성화
- `diarizer.py`는 이미 pyannote 기반으로 구현됨
- pyannote-audio 설치 + HuggingFace 토큰 필요
- `pipeline.py` 또는 `telegram_bot.py`에서 `diarize()` → `assign_speakers()` 호출 추가

## 테스트

```bash
.venv/bin/pytest src/tests/ -v   # 전체 테스트 (153개+)
.venv/bin/pytest src/tests/test_transcriber.py  # 모듈별
```

테스트 파일: `src/tests/test_*.py`
패턴: pytest + mock 기반, 외부 의존성(Whisper, API) 없이 실행 가능
