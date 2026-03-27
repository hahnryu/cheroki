# Cheroki — CLAUDE.md

음성 전사 파이프라인. Hahnness 생태계의 채록 에이전트.
이 프로젝트는 `d:/projects/cheroki/`에 산다.

## 빌드 모드

이 프로젝트는 Planner-Developer-Validator 자율 빌드 하니스로 운영된다.

### 역할 전환 규칙

**Planner** (첫 실행 시, 또는 새 Phase 시작 시):
- README.md의 해당 Phase 항목을 읽는다
- features.json에 구체적 기능 목록을 작성한다 (각 기능은 독립적으로 테스트 가능해야 함)
- 기술 구현 세부사항보다 "무엇이 완성되어야 하는가"에 집중한다
- 잘못된 기술 가정이 하류로 전파되지 않도록, 구현 방법은 Developer에게 맡긴다

**Developer** (기능 구현):
- features.json에서 다음 미완료 항목을 선택한다
- 한 번에 하나의 기능만 구현한다
- 구현 완료 시 반드시 테스트를 작성하고 실행한다
- 기능 완료마다 git commit + claude-progress.txt 업데이트
- 큰 결정이 필요하면 (예: DB 스키마, API 설계) 멈추고 사용자에게 질문한다

**Validator** (검증):
- 매 기능 완료 후 실제 실행하여 검증한다
- 단위 테스트 + 통합 테스트
- 실패 시 Developer로 되돌아간다
- 통과 시 features.json에 완료 표시 후 다음 기능으로

### 진행 추적

claude-progress.txt를 항상 최신 상태로 유지한다:
```
## 현재 Phase: 0
## 현재 기능: [기능명]
## 상태: [구현중 / 검증중 / 완료]
## 완료된 기능:
- [x] 기능1 (커밋 해시)
- [x] 기능2 (커밋 해시)
## 다음 기능: [기능명]
## 메모: [현재 맥락, 주의사항]
```

### YOLO 모드 (기본)

중간에 멈추지 않고 Phase 끝까지 한 번에 간다.
- proceed 여부를 묻지 않는다
- 기술적 판단은 스스로 내린다
- Phase 완료 시 결과 보고만 한다
- 진척도를 %로 표시한다

### 사용자 확인 필요 지점 (이것만 멈추고 질문)

- 외부 API 키/토큰 필요 시
- 프라이버시에 영향을 주는 결정
- 돈이 드는 외부 서비스 연동

## 코드 규칙

1. Python 3.11+, type hints 필수
2. 모든 경로는 설정 파일(config.yaml)에서 관리. 하드코딩 금지
3. 각 모듈은 독립적으로 테스트 가능해야 한다
4. 에러 시 음성 원본이 손상되거나 삭제되는 일은 절대 없어야 한다
5. 로그는 구조화된 형식 (structlog)
6. git commit은 기능 단위. 메시지는 한국어 가능

## 디렉토리 구조

```
cheroki/
├── CLAUDE.md              ← 이 파일
├── README.md              ← 프로젝트 개요, Phase 계획
├── claude-progress.txt    ← 진행 추적 (자동 관리)
├── features.json          ← 기능 목록 (Planner가 작성)
├── config.yaml            ← 경로, 설정
├── src/
│   ├── cheroki/
│   │   ├── __init__.py
│   │   ├── transcriber.py     ← Whisper 전사 엔진
│   │   ├── storage.py         ← 파일 저장/관리
│   │   ├── reviewer.py        ← 의심 구간 추출, 질문 생성
│   │   ├── corrector.py       ← 교정 반영
│   │   ├── exporter.py        ← SRT, MD 산출물 생성
│   │   ├── corpus.py          ← 교정 쌍 코퍼스 관리
│   │   ├── metadata.py        ← 메타데이터 추출
│   │   ├── dictionary.py      ← 고유명사 사전
│   │   └── watcher.py         ← 폴더 감시 (파일 수신)
│   └── tests/
├── data/                  ← .gitignore 대상
│   ├── originals/         ← 원본 음성 (절대 삭제 안 함)
│   ├── transcripts/       ← 전사 결과 (1차, 최종)
│   ├── corrections/       ← 교정 이력
│   ├── corpus/            ← 음성+전사 쌍 코퍼스
│   └── exports/           ← SRT, MD 산출물
├── dictionary/            ← 고유명사 사전
├── pyproject.toml
└── .gitignore
```

## 연동

- **Hahnness vault**: 최종 MD 산출물을 vault의 적절한 폴더로 복사 (경로는 config.yaml)
- **Siltarae**: Phase 4에서 API 연동 (최종 녹취록 → Fragment)
- **텔레그램**: Phase 4에서 봇 연동 (파일 수신 → data/originals/)

## 프라이버시

- data/ 폴더는 절대 git에 올리지 않는다
- Whisper는 반드시 로컬 실행
- Claude API 호출 시 음성 원본은 전송하지 않는다. 텍스트만.
- 모든 데이터는 로컬 디스크에만 존재한다
