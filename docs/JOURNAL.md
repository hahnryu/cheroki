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

### 밤 세션: 배포 + 품질 이슈 발견

**배포 실행**:
- 서버에 새 코드 tar-over-ssh 전송, uv pip install → 41 테스트 통과
- 마이그레이션 dry-run → 실제 실행: 3건 이동(data/260420/{ah114d,v3gbjd,rwgr66}_raw.*), 2건 메타만 업데이트
- 봇 재기동 (여전히 클라우드 API, 20MB 한도)

**중복 실패 이슈**:
- tar에 `.env`를 exclude 안 해서 배포 시 서버 `.env`가 노트북 버전으로 덮어써짐
- LOCAL_API_URL이 다시 `http://localhost:8081`로 돌아가 사용자 테스트 3건이 또 404로 실패
- 수동으로 `.env` 수정 + 봇 재시작 후 정상화
- 배포 스크립트에 `.env` exclude 추가 필요 (Task 22)

**전사 품질 이슈 발견**:
사용자가 4/20 회의록(rwgr66, 25분, 2명)을 검토한 결과 심각한 품질 문제:
- 고유명사 다수 오인식 (bstage→"비슷해지"/"리스테이저", 야반스→"양반들"/"약관스타", wind and flow→"민드앤플로우"/"윤젠포그", 풍류→"통류", 하회→"하우웨이")
- 화자분리 부분 실패 ("범선"의 "선"이 화자 라벨로 오인식, "음/응" 추임새가 "울큰/울준"으로)
- 숫자·날짜 오인식 (6월→2월 등)
- 구조 파괴 구간 다수
- 그래도 골자는 추출 가능한 수준

**원인 추정**: Deepgram Nova-2의 한국어 모델이 일반 대화용으로는 쓸 만하지만 도메인 어휘·구술사 같은 specialized 음성에는 약함. Keywords 파라미터로 고유명사 일부 개선 가능하지만 구조적 한계는 provider 교체·AI 교정으로만 해결.

**provider 비교 조사 결과** (Task 18으로 내일 실험 예정):
- **Naver CLOVA Speech**: 한국어 네이티브, 분당 약 30원(Deepgram 11원의 3배), 국내 데이터 체류, 네이버 클라우드 플랫폼 가입 필요. 한국어로는 최상급 기대.
- **ElevenLabs Scribe v2**: 분당 약 9.3원(최저가), 한국어 WER 10~20%("Good" 등급), keyterm 1000개, SOC2/GDPR/HIPAA/Zero Retention 모드. 다국어 모델이지만 최신 벤치마크 상회.
- **Deepgram Nova-2**: 현재 사용 중, 품질 이슈 확인.
- **전략**: 같은 파일 3 provider 병렬 돌려 비교 후 기본 provider 결정.

**내일 할 일** (우선순위):
1. provider 비교 실험 (Task 18) — **최우선**. 이거 결과에 따라 후속 결정 달라짐
2. 기본 provider 확정 → 관련 Task (19 또는 provider 교체) 진행
3. AI 교정 모듈 착수 (Task 20) — 어떤 provider든 교정 루프는 유용
4. 실패 레코드 정리 (Task 21)
5. 배포 스크립트 정리 (Task 22)
6. Local Bot API 2GB 모드 (Task 17) — provider 문제 해결된 뒤에

**끝날 때 상태**:
- 서버 봇 PID 26394 (클라우드 API, 20MB 한도, 정상 가동 중)
- 로컬 커밋: `ec965f2` (MVP) + `d1bc055` (새 레이아웃). 푸시 안 됨 (GitHub 레포 없음)
- 테스트 41개 통과, 린트 깨끗
- data/260420/ 에 실제 녹취 3건 (품질 낮지만 참조용 보존)

---

## 2026-04-21 — provider 비교 실험, Scribe 확정

### 아침 세션: Task 18 provider 비교 + Scribe 확정

**목표**: 4/20에 드러난 Deepgram 한국어 품질 이슈를 두고, ElevenLabs Scribe v2와 비교해 기본 provider 결정.

**구현**:
- `core/transcribers/scribe.py` — ElevenLabs `/v1/speech-to-text` 래퍼. scribe_v2 + diarize + timestamps_granularity=word. 응답의 word 배열을 speaker_id 경계로 Utterance에 묶고, 단어들의 평균 logprob을 exp하여 [0,1] confidence로 변환. audio_event 토큰은 speaker 판단에서 제외.
- httpx 함정: AsyncClient에서 `data=list[tuple]`로 multipart form을 넘기면 sync stream 경로로 빠져 `Attempted to send an sync request with an AsyncClient instance` 에러. `data=dict` + dict value로 list를 주는 방식으로 해결.
- `scripts/compare_providers.py` — 파일 하나를 받아 Deepgram과 Scribe를 `asyncio.gather`로 병렬 호출, `<stem>.{provider}.{srt,md,txt,raw.json}`로 저장. 정식 저장 파이프라인·SQLite는 건드리지 않는 사이드 트랙.
- 단위 테스트 7개 (speaker 매핑 안정성·audio_event 스킵·confidence 클램프·빈 응답 등).

**실험 결과 (rwgr66_raw.ogg, 25분)**:
| 항목 | Deepgram Nova-2 | Scribe v2 |
|---|---|---|
| 처리 시간 | 9.0s | 68.6s |
| 화자 수 | 3 | 3 |
| txt 크기 | 15.3 KB | 22.0 KB |
| utterance 수 | 426 | 331 (내 grouping 기준 차이) |

- Scribe가 영문 고유명사(UNESCO) 정확 표기, 문장 단위 묶기 자연스러움, 리액션·추임새 포착("내가, 내가, 내가 대충 만들었거든?") 등에서 우위.
- Deepgram은 속도(7.6배 빠름)와 자체 utterance 구획 제공이 장점.
- JOURNAL 4/20 밤 세션에 기록된 오인식 단어(bstage, 야반스, 풍류, 하회 등)는 rwgr66엔 없음. 그 케이스는 같은 날 `0420_jeonbeomseon_wf_hoeyi_m4a`에서 나온 걸로 추정. 추후 재검증 여지.

**결정**: 기본 provider = Scribe. CLAUDE.md 규칙상 `config.yaml`은 금지이므로 `.env`에 `STT_PROVIDER` 변수 추가, `_default_transcriber()`에서 분기. `STT_PROVIDER=deepgram`으로 언제든 되돌릴 수 있음.

**배포**:
- tar 패키징 시 `.env` 명시 제외(4/20 밤 재발 방지 이슈).
- 서버 `~/projects/cheroki`에 코드 전송, `.env`에 `STT_PROVIDER=scribe` + `ELEVENLABS_API_KEY` append (stdin 경유, ps/history 노출 없음).
- 기존 봇(PID 26394) SIGTERM 후 새 봇(PID 31179) 클라우드 Bot API 모드 유지로 재기동. 로그 확인 완료.

**메트릭**:
- 52 테스트 통과 (+11: scribe 파싱 7 + provider 분기 4)
- 로컬 커밋: `c463a01` (Scribe transcriber) + (후속, 이 세션)
- ElevenLabs 호출 비용: rwgr66 1건 ~240원 추정

**다음**: 사용자 요청에 따라 Task 17(Local Bot API 2GB 모드) 착수 — docker-compose `--local` + bind mount + aiogram `local_mode=True` + uid 정합.

### 오후 세션: Task 17 Local Bot API 2GB 모드 전환

**목표**: Telegram 20MB 한도 우회. Local Bot API Server 컨테이너를 `--local`로 돌리고, 봇이 컨테이너 저장 파일을 호스트에서 직접 읽도록 bind mount + aiogram 경로 매핑.

**구현 변경**:
- `docker-compose.yml`: named volume → `./data/tg-api` bind mount. 127.0.0.1:8081로 포트 제한(외부 차단).
- `config.Config.local_api_files_dir`: 호스트의 bind mount target 경로 필드.
- `interfaces/telegram/bot.py`: `TelegramAPIServer.from_base(..., is_local=True, wrap_local_file=SimpleFilesPathWrapper(server=/var/lib/telegram-bot-api, local=호스트경로))`. 봇이 `getFile` 응답의 컨테이너 내부 경로를 호스트 경로로 변환해 읽음.
- `scripts/announce.py`: 허용 사용자 전원에게 Telegram sendMessage. 봇이 내려가 있어도 작동(API 직접 호출). 배포·장애·모드 전환 공지용.

**시행착오 2가지 (JOURNAL 예언대로 uid 이슈)**:
1. **compose의 `command:` 리스트를 entrypoint가 무시** — `aiogram/telegram-bot-api` 이미지의 `/docker-entrypoint.sh`가 자체적으로 `TELEGRAM_*` env 변수만 읽어 CUSTOM_ARGS 구성. `--local` 플래그는 `TELEGRAM_LOCAL=1` env로 활성화해야 함. compose 로그에 `--local`이 안 찍혀서 발견.
2. **컨테이너가 쓰는 파일이 600 (umask 077)** — bind mount로 호스트에 노출돼도 봇(다른 uid)이 못 읽음. `entrypoint:` 오버라이드로 `umask 022 && exec /docker-entrypoint.sh` 래핑 → 미디어 파일 644로 생성, other(봇) 읽기 OK.

**우연의 행운**: telegram-bot-api가 세션 디렉토리(`<bot_token>/`)를 `drwxr-x---` (750)로 만듦. 호스트에서 `messagebus:lxd` 소유로 보이는데 hahnryu가 이미 **lxd 그룹 멤버**라 group r-x로 접근 가능. ACL 추가 설정 불필요.

**검증**:
- 컨테이너 cmdline에 `--local --verbosity=1` 확인.
- `__umask_test` 파일 644 생성, bind mount 양쪽에서 동일하게 보임.
- 봇 로그: `Local Bot API 서버 사용: http://localhost:8081 (files: /var/lib/telegram-bot-api ↔ /home/hahnryu/projects/cheroki/data/tg-api)` + `Start polling`.
- `announce.py --prefer-local`로 로컬 서버 경유 sendMessage 200 OK → 공지 2회차 전달.

**공지 흐름**:
1. 전환 직전 (봇 클라우드 모드 살아있을 때): "🔧 봇 업데이트: 2GB 모드 전환 중..." 클라우드 API로 발송.
2. Telegram `logOut` → docker compose down → named volume 삭제 → bind mount 준비 → compose up (`--local`) → 봇 재기동.
3. 전환 완료: "✅ 2GB 모드 전환 완료..." 로컬 서버로 발송 (local 가동 확인 겸).

**상태**:
- 서버 봇 PID 37248, Local Bot API 모드, 2GB 제한 활성.
- 테스트 대기: 20MB 초과 파일을 사용자가 전송해 end-to-end 확인 필요.
- 커밋 `c5a1ca5` + `918acf1` (compose 수정).
- 52 테스트 통과 유지.

**남은 관찰**:
- 이중 저장 (Docker bind mount의 원본 + 봇이 `data/YYMMDD/`로 복사한 사본). 디스크 배증. 필요시 `bot.delete_file()` 후처리 추가 (Phase 2).
- 운영 관례로 systemd 유닛 도입은 여전히 미룸 (현재 nohup + bot.pid).

---

## 2026-04-22 — cenote 통합 논의 + 파일명 한글화

**세션 초중반**: cenote(사용자 개인 vault + 보리 에이전트) 통합 설계. 세 갈래로 정리됨.

1. **저장 경로 통합**: cheroki의 `DATA_DIR`을 `~/cenote/10_fragments/`로 직접 지정하는 방향. 폴더 포맷 `YYYYMMDD(요일)`, 파일명에 날짜 필수. `.env`로 옵션화해서 cheroki 자체 범용성은 유지.
2. **Scribe keyterms = cenote memory**: `nightly_distill`이 `30_memory/`를 스캔해 `90_minions/index/keyterms.txt` 생성, cheroki가 매 전사마다 주입. 정적 파일 방식.
3. **`/review` skill**: `_raw.md`는 영구 보존, 보리가 대화형으로 교정해 `_edited.md` 생성. cheroki 무변경, 보리 쪽 skill.

추가 논의: cheroki 봇 프로세스 중지하고 cenotebot(Telegram 창구)이 cheroki 라이브러리 직접 호출하는 통합안. Local Bot API라 2GB 처리에도 영향 없음. 결정 유보.

"복잡하다"는 사용자 판단으로 **cenote 통합 전체를 보류**. 보리 전달용 통합 인계문(자기소개 + 의도 정리 + 시방서)만 작성해두고 실제 전달은 안 함. 나중에 재개 시점에 활용.

### 저녁 세션: 파일명 한글화 (단일 작업)

**배경**: 영문 romanize 슬러그(`0420_bonadaehwa`)가 캡션 원문(`0420 보나대화`)과 대조해 읽기 어려움. 단순 변경으로.

**구현**:
- `src/cheroki/naming.py` — `romanize()` 제거, `safe_slug()` 신설. 파일시스템 금지 문자(`/ \ : * ? " < > |` + 제어문자)만 제거하고 한글·영문·숫자는 유지. 공백은 기존처럼 언더스코어.
- `unidecode` 의존성 제거 (pyproject.toml).
- 테스트 한글 기대값으로 교체. 54개 통과(+3-3).
- SQLite `romanized_slug` 컬럼명은 잔재로 유지(내용만 한글로 바뀜). 스키마 리네임은 과잉.
- CLAUDE.md·README.md·CHANGELOG.md 관련 언급 갱신. 과거 JOURNAL은 그대로.

**예**:
```
기존: 0420_bonadaehwa_raw.m4a
신규: 0420_보나대화_raw.m4a
```

**배포**: 서버 코드 갱신 + 봇 재시작(PID 50398). editable install이라 즉시 반영. Local Bot API 2GB 모드 유지.

**커밋**: `f107ce5` (+ 푸시 완료).

**남은 관심**: cheroki 봇 관련 운영 지식을 `cenote/90_minions/bots/cheroki/`에 **SOUL.md / operations.md / integration.md** 형태로 두는 구조 제안만 해둠. 코드·데이터는 `~/projects/cheroki/` 그대로. 구현은 cenote 통합 논의 재개 시에.

---

## 로드맵 (요약)

- **Phase 1 (끝남)**: MVP — 전사 + SRT/MD/TXT + Telegram 봇 + CLI + 네이밍 규약
- **Phase 1.5 (진행 중)**: Local Bot API 2GB 모드 안정화
- **Phase 2**: 화자 이름 치환 모듈, AI 교정 루프, 캡션 파싱 강화(장소 추출)
- **Phase 3**: 실타래 본체 연동 (Graphiti), vault 싱크 도구
- **Phase 4**: 하회 어르신 아카이브, 구술사 전집, 파인튜닝 데이터셋

상세는 [PLAN_v3.md](PLAN_v3.md).
