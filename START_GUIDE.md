# Cheroki 자율 빌드 시작 가이드

## 사전 준비

### 1. 서버 환경 확인
```bash
# Python 3.11+ 확인
python3 --version

# GPU 확인 (Whisper 속도에 영향)
nvidia-smi

# 디스크 여유 공간 (음성 파일 + Whisper 모델)
df -h
```

### 2. 프로젝트 폴더 생성
```bash
mkdir -p d:/projects/cheroki
# 이 폴더에 CLAUDE.md와 README.md를 복사
```

### 3. Claude Code 실행
```bash
cd d:/projects/cheroki
claude
```

### 4. 첫 프롬프트 (이것만 입력하면 알아서 시작)

아래 프롬프트를 Claude Code에 붙여넣으면 Planner 모드로 시작합니다:

---

```
CLAUDE.md와 README.md를 읽어라.

너는 Cheroki 프로젝트의 빌더다. Planner-Developer-Validator 하니스에 따라 자율적으로 작업한다.

지금 Phase 0(코어)을 시작한다.

1. [Planner] README.md의 Phase 0 항목을 읽고, features.json에 구체적 기능 목록을 작성하라. 각 기능은 독립적으로 테스트 가능해야 한다.

2. [Developer] features.json의 첫 번째 기능부터 순서대로 구현하라. 한 번에 하나씩. 완료마다 테스트 실행, git commit, claude-progress.txt 업데이트.

3. [Validator] 매 기능 완료 후 실제 실행하여 검증. 실패 시 수정. 통과 시 다음으로.

Phase 0이 끝나면 멈추고 보고하라.

config.yaml에 들어갈 경로 설정:
- 원본 음성 저장: d:/cheroki-data/originals/
- 전사 결과: d:/cheroki-data/transcripts/
- 교정 이력: d:/cheroki-data/corrections/
- 코퍼스: d:/cheroki-data/corpus/
- 산출물: d:/cheroki-data/exports/
- Hahnness vault: [여기에 vault 경로 입력]
- Whisper 모델: large-v3 (GPU 있으면), medium (없으면)

시작하라.
```

---

## 이후 Phase 진행

Phase 0 완료 보고를 받은 후, 다음 프롬프트로 Phase 1을 시작:

```
Phase 0 완료를 확인했다. Phase 1(교정 루프)을 시작하라. 같은 하니스 규칙을 따른다.
```

## Hahnness ONTOLOGY.md 업데이트

Cheroki가 확정되면, Hahnness vault의 ONTOLOGY.md에 아래를 추가:

```markdown
├── [도구] Cheroki (채로키, 採錄)
│   │  음성 → 정확한 텍스트. 전사 파이프라인.
│   │  교정 쌍 누적 → 음성 코퍼스 데이터.
│   │  d:/projects/cheroki/
│   │
│   └──→ Siltarae의 앞단 입력 채널
│   └──→ 뿌리깊은나무의 원본 데이터 소스
```
