# Changelog

이 파일은 주요 변경 사항을 기록한다. [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 형식을 따르며, 버전은 [Semantic Versioning](https://semver.org/lang/ko/)을 따른다.

## [0.1.0] — 2026-04-21

첫 공개 버전. MVP + Phase 1.5까지.

### Added

- **Core 전사 라이브러리** (`from cheroki import transcribe_audio`)
  - `Transcriber` Protocol + `TranscriptionResult` + `Utterance`, `TranscriptionMetadata` 타입
  - SRT / Markdown (YAML frontmatter 포함) / TXT / provider 원본 JSON 네 가지 산출 포맷
  - `DATA_DIR/YYMMDD/<slug>_raw.<ext>` 저장 규약 (self-describing, 하류 도구 친화)
- **STT provider 두 가지**
  - `ScribeTranscriber` (ElevenLabs Scribe v2) — 한국어 구술사 품질 우위, 기본값
  - `DeepgramTranscriber` (Nova-2) — 속도 우위, 보조 옵션
  - `.env`의 `STT_PROVIDER`로 스위칭 (`scribe` / `deepgram`)
- **Storage 계층**
  - `SQLiteStore` — 메타데이터 + 상태 인덱싱 (pending/processing/completed/failed)
  - `FileStore` — 날짜·슬러그 기반 경로 계산
  - 6자리 Crockford base32 short ID
- **Naming 모듈**
  - 캡션에서 날짜(YYMMDD / YYYY-MM-DD / YYYY.MM.DD 등) 자동 추출
  - 캡션 기반 슬러그 생성. 한글·영문 그대로 유지, 파일시스템 금지 문자만 제거 (2026-04-22부터)
  - `_raw` 접미어로 1차 채록 산출물 표시 (후속 모듈은 `_edited`, `_named` 등)
- **Telegram 봇** (`@cheroki_siltarebot`, aiogram v3)
  - `/start`, `/help`, `/last`, `/get <id>`, `/status <id>` 명령어
  - **Local Bot API 모드 2GB 지원** — `docker compose up -d`로 `--local` 서버 기동, bind mount로 호스트 봇이 파일에 직접 접근
  - **실시간 진행 상황 알림** — 수신 즉시 파일명·크기·길이·저장 경로 답장, 다운로드·전사 단계마다 경과 시간을 7초 간격으로 edit 업데이트
  - 허용 사용자 ID 기반 접근 제어
- **CLI** (`cheroki` 명령어)
  - `cheroki transcribe <audio>` — 단일 파일 녹취
  - `cheroki bot` — 봇 기동
  - `cheroki migrate` — 구 레이아웃 → 신 레이아웃 이주
  - `cheroki info <id>` — 레코드 조회
- **운영 스크립트**
  - `scripts/compare_providers.py` — 동일 오디오에 Deepgram·Scribe 병렬 호출, `<stem>.{provider}.{srt,md,txt,raw.json}`로 저장·비교
  - `scripts/announce.py` — 허용 사용자 전원에게 Telegram sendMessage (봇 다운타임에도 작동)
- **문서**
  - `docs/PLAN_v3.md` 기획안
  - `docs/JOURNAL.md` 개발 저널 (2026-04-20 / 2026-04-21)
  - `docs/SETUP.md`, `docs/DEPLOY.md`, `docs/CONCEPTS.md`
- **테스트** — pytest 52개 (파싱·grouping·storage·naming·provider 분기 등)

### Security

- `.env` 및 API 키·토큰·credentials는 `.gitignore`로 커밋 원천 차단
- `.env.example`만 공개 (실제 값 없음)
- 커밋 히스토리 스캔 — 실제 시크릿 노출 0건 확인 후 공개

### Known Limitations

- Scribe 처리 속도가 Deepgram의 ~7배 느림 (25분 오디오 기준 9s vs 68s). 품질 우선 선택.
- Local Bot API 모드에서 같은 파일이 **Docker bind mount**와 **`data/YYMMDD/` 봇 사본** 두 곳에 저장됨 (디스크 2배). `bot.delete_file()` 후처리는 추후.
- 2GB 초과 파일은 Telegram 자체 제한으로 불가. Scribe는 3GB까지 수용.
- 화자분리가 종종 1명 과잉 추정 (rwgr66에서 실제 2명을 3명으로 잡음). AI 교정 루프(Phase 2)로 보완 예정.

[0.1.0]: https://github.com/hahnryu/cheroki/releases/tag/v0.1.0
