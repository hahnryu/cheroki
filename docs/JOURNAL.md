# Cheroki 개발 저널

세션별 맥락. "왜 이렇게 됐는지" 나중에 잊지 않으려고 남긴다.

---

## 2026-04-20 — v0.1 MVP + 새 레이아웃

### 아침 세션: 레거시 폐기, 새 cheroki v3 구축

**왜**: 이전 cheroki(`/mnt/d/projects/cheroki_legacy/`)는 로컬 Whisper CPU 의존(30분 파일 → 10~20분 처리)과 범위 과대(전사+교정+산출물+학습+코퍼스+CLI+웹+봇)로 실패. 워크플로우 붕괴 후 사용 중단.

**결정**: 범위 축소 + Deepgram Nova-2로 교체.
- 포함: Telegram 봇, Deepgram 전사, SRT/MD/TXT, SQLite, Local Bot API 서버 (2GB 대응)
- 제외 (나중에 별도 모듈): AI 교정 루프, 화자 이름 치환, Graphiti 연동, 고유명사 사전

**구현**:
- core (types, result, exporter, transcribers/deepgram) + storage (sqlite, fs) + interfaces/telegram
- 21 단위테스트 통과
- 초기 커밋 `ec965f2`

### 오후 세션: 서버 배포 + 파이프라인 검증

**서버**: `hahoegenesis` (Ubuntu 24.04, Tailscale 100.113.208.55)
**배포 흐름**: Docker 설치(sudo 1회) → uv 설치 → tar-over-ssh로 코드 전송 → venv → docker compose up → 봇 기동

**404 이슈**: Local Bot API 서버가 `--local` 플래그 없이는 HTTP로 파일을 서빙하지 않음. 파일은 `/var/lib/telegram-bot-api/<token>/voice/file_X.oga`에 존재하지만 `http://localhost:8081/file/bot<token>/<path>` 경로가 전부 404.

**임시 대응**: .env의 `LOCAL_API_URL=` 비워서 클라우드 Bot API로 fallback(우리 코드가 자동 분기). 20MB 제한 하에서 파이프라인 검증 성공 — 짧은 voice 4건 녹취, SRT에 S0/S1 화자 분리 확인(25분 2명 대화 건에서).

**실데이터**:
- `rwgr66` · 25분 · 2명 → 화자분리 OK
- `v3gbjd` · 11분 · 1명
- `ah114d` · 14초 · 1명

### 저녁 세션: 새 폴더 레이아웃 + 네이밍 규약 도입

**왜**: 사용자 요청. short ID 기반 파일명(`ab7f3c.srt`)은 내부용으로만 충분하지만 실제 저장 구조는 사람이 바로 알아볼 수 있는 날짜·슬러그 기반이어야 함. 이유: 앞으로 교정 모듈, 이름지정 모듈 등이 cheroki의 폴더 구조를 입력으로 쓸 예정. cheroki가 깔끔하고 self-describing한 원자료 저장소 역할.

**새 레이아웃**:
```
DATA_DIR/YYMMDD/<slug>_raw.{m4a,srt,md,txt,json}
```

**네이밍 규약**:
- `YYMMDD` 폴더: 캡션에서 날짜 추출 시도 (`260420`, `2026-04-20`, `2026.04.20` 등), 실패 시 Telegram 수신 시각 또는 파일 mtime
- `<slug>`: 캡션에서 날짜 제거 후 romanize(unidecode) → 소문자 ASCII + `_` 구분. 캡션 없으면 원본 파일명(제네릭 `voice_N`은 건너뜀). 그것도 없으면 short ID
- `_raw` 접미어: 1차 채록 산출물 표시 (교정본은 `_edited`, 이름지정본은 `_named` 등으로 구분)

**구현 변경**:
- `src/cheroki/naming.py` — 캡션 파싱, romanize, slug build
- `FileStore` — 경로 계산 전면 재작성 (date + slug 기반)
- SQLite 스키마 확장: `recording_date, romanized_slug, file_format, place, source, received_at`. 기존 DB에 대해 `ALTER TABLE ADD COLUMN` 자동 마이그레이션(idempotent)
- `cheroki.migrate` 모듈 — 구 `data/uploads/<id>.ext` + `data/exports/<id>.{srt,md,txt,raw.json}` → 신 레이아웃으로 이동. dry-run 지원
- CLI 신설: `cheroki {transcribe,bot,migrate,info}` — `cheroki transcribe <file>` 단일 파일 녹취
- Telegram handler 업데이트 — 새 레이아웃 적용
- Markdown frontmatter 확장 (title, recording_date, record_id, slug, source, caption, original_filename, file_format 등)
- 41 단위테스트 통과 (+20), 린트 깨끗

**다음**: 서버 재배포 + 실데이터 4건 마이그레이션 → Local Bot API 2GB 모드 전환 작업.

---

## 로드맵 (요약)

- **Phase 1 (끝남)**: MVP — 전사 + SRT/MD/TXT + Telegram 봇 + CLI + 네이밍 규약
- **Phase 1.5 (진행 중)**: Local Bot API 2GB 모드 안정화
- **Phase 2**: 화자 이름 치환 모듈, AI 교정 루프, 캡션 파싱 강화(장소 추출)
- **Phase 3**: 실타래 본체 연동 (Graphiti), vault 싱크 도구
- **Phase 4**: 하회 어르신 아카이브, 구술사 전집, 파인튜닝 데이터셋

상세는 [PLAN_v3.md](PLAN_v3.md).
