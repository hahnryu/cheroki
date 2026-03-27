"""코퍼스 데이터셋 모듈 — 패키징, 메타데이터 태깅, 내보내기."""

from __future__ import annotations

import csv
import io
import json
import shutil
import structlog
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

from cheroki.corpus import load_corpus_pairs, list_corpus_files

logger = structlog.get_logger()


# ── F5-1: 코퍼스 데이터 패키징 ───────────────────────

@dataclass
class CorpusPackage:
    """코퍼스 패키지 — 하나의 전사에 대한 전체 데이터."""
    file_id: str
    original_audio: str      # 원본 음성 경로
    raw_transcript: str      # 1차 전사 (틀린 버전) 경로
    corrected_transcript: str  # 교정 후 전사 경로
    corrections: str         # 교정 이력 경로
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_package(
    file_id: str,
    config: dict[str, Any],
) -> CorpusPackage | None:
    """file_id에 대한 코퍼스 패키지를 구성한다.

    originals/, transcripts/, corrections/ 에서 관련 파일을 찾는다.
    """
    originals_dir = Path(config["paths"]["originals"])
    transcripts_dir = Path(config["paths"]["transcripts"])
    corrections_dir = Path(config["paths"]["corrections"])

    # 원본 메타데이터
    meta_path = originals_dir / f"{file_id}.meta.json"
    if not meta_path.exists():
        return None

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    audio_path = meta.get("stored_path", "")

    # 전사 결과
    raw_path = transcripts_dir / f"{file_id}.transcript.json"
    final_path = transcripts_dir / f"{file_id}_final.transcript.json"
    corr_path = corrections_dir / f"{file_id}.corrections.json"

    return CorpusPackage(
        file_id=file_id,
        original_audio=audio_path,
        raw_transcript=str(raw_path) if raw_path.exists() else "",
        corrected_transcript=str(final_path) if final_path.exists() else "",
        corrections=str(corr_path) if corr_path.exists() else "",
        metadata=meta,
    )


def export_package(
    package: CorpusPackage,
    output_dir: Path,
) -> Path:
    """코퍼스 패키지를 하나의 디렉토리에 모아 저장한다."""
    output_dir = Path(output_dir)
    pkg_dir = output_dir / package.file_id
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # 파일 복사
    for label, src_path in [
        ("audio", package.original_audio),
        ("raw_transcript", package.raw_transcript),
        ("corrected_transcript", package.corrected_transcript),
        ("corrections", package.corrections),
    ]:
        if src_path and Path(src_path).exists():
            dest = pkg_dir / f"{label}{Path(src_path).suffix}"
            shutil.copy2(src_path, str(dest))

    # 매니페스트
    manifest = package.to_dict()
    (pkg_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return pkg_dir


# ── F5-2: 메타데이터 태깅 ────────────────────────────

@dataclass
class CorpusTag:
    """코퍼스 메타데이터 태그."""
    file_id: str
    speaker_age: str = ""         # "20s", "30s", "40s", ...
    speaker_gender: str = ""      # "M", "F", "other"
    dialect: str = ""             # "표준어", "경상도", "전라도", ...
    topic: str = ""               # 주제
    recording_quality: str = ""   # "high", "medium", "low"
    duration_seconds: float = 0.0
    custom: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def save_tag(tag: CorpusTag, tags_dir: Path) -> Path:
    """태그를 JSON으로 저장."""
    tags_dir = Path(tags_dir)
    tags_dir.mkdir(parents=True, exist_ok=True)
    path = tags_dir / f"{tag.file_id}.tag.json"
    path.write_text(json.dumps(tag.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_tag(path: Path) -> CorpusTag:
    """저장된 태그를 로드."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return CorpusTag(
        file_id=data["file_id"],
        speaker_age=data.get("speaker_age", ""),
        speaker_gender=data.get("speaker_gender", ""),
        dialect=data.get("dialect", ""),
        topic=data.get("topic", ""),
        recording_quality=data.get("recording_quality", ""),
        duration_seconds=data.get("duration_seconds", 0.0),
        custom=data.get("custom", {}),
    )


def load_all_tags(tags_dir: Path) -> list[CorpusTag]:
    """디렉토리 내 모든 태그를 로드."""
    tags_dir = Path(tags_dir)
    if not tags_dir.exists():
        return []
    return [load_tag(p) for p in sorted(tags_dir.glob("*.tag.json"))]


# ── F5-3: 데이터셋 내보내기 ──────────────────────────

def export_jsonl(
    corpus_dir: Path,
    output_path: Path,
    tags_dir: Path | None = None,
) -> Path:
    """코퍼스를 JSON Lines 형식으로 내보낸다.

    각 줄: {"file_id", "original", "corrected", "tags": {...}}
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 태그 로드
    tags_map: dict[str, CorpusTag] = {}
    if tags_dir and Path(tags_dir).exists():
        for tag in load_all_tags(tags_dir):
            tags_map[tag.file_id] = tag

    lines: list[str] = []
    for path in list_corpus_files(corpus_dir):
        data = load_corpus_pairs(path)
        file_id = data.get("file_id", "")
        tag = tags_map.get(file_id)

        for pair in data.get("pairs", []):
            entry = {
                "file_id": file_id,
                "original": pair["original"],
                "corrected": pair["corrected"],
                "language": data.get("language", "ko"),
            }
            if tag:
                entry["tags"] = {
                    "speaker_age": tag.speaker_age,
                    "speaker_gender": tag.speaker_gender,
                    "dialect": tag.dialect,
                    "topic": tag.topic,
                }
            lines.append(json.dumps(entry, ensure_ascii=False))

    output_path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
    logger.info("dataset_exported_jsonl", path=str(output_path), entries=len(lines))
    return output_path


def export_csv(
    corpus_dir: Path,
    output_path: Path,
    tags_dir: Path | None = None,
) -> Path:
    """코퍼스를 CSV 형식으로 내보낸다."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tags_map: dict[str, CorpusTag] = {}
    if tags_dir and Path(tags_dir).exists():
        for tag in load_all_tags(tags_dir):
            tags_map[tag.file_id] = tag

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["file_id", "original", "corrected", "language", "speaker_age", "dialect", "topic"])

    count = 0
    for path in list_corpus_files(corpus_dir):
        data = load_corpus_pairs(path)
        file_id = data.get("file_id", "")
        tag = tags_map.get(file_id)

        for pair in data.get("pairs", []):
            writer.writerow([
                file_id,
                pair["original"],
                pair["corrected"],
                data.get("language", "ko"),
                tag.speaker_age if tag else "",
                tag.dialect if tag else "",
                tag.topic if tag else "",
            ])
            count += 1

    output_path.write_text(buf.getvalue(), encoding="utf-8")
    logger.info("dataset_exported_csv", path=str(output_path), entries=count)
    return output_path


def export_huggingface(
    corpus_dir: Path,
    output_dir: Path,
    tags_dir: Path | None = None,
    dataset_name: str = "cheroki-corpus",
) -> Path:
    """HuggingFace datasets 형식으로 내보낸다.

    구조:
    output_dir/
      dataset_info.json
      data/
        train.jsonl
    """
    output_dir = Path(output_dir)
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # train.jsonl 생성
    train_path = export_jsonl(corpus_dir, data_dir / "train.jsonl", tags_dir)

    # 줄 수 계산
    n_lines = 0
    if train_path.exists():
        text = train_path.read_text(encoding="utf-8").strip()
        n_lines = len(text.split("\n")) if text else 0

    # dataset_info.json
    info = {
        "dataset_name": dataset_name,
        "description": "Cheroki 음성 전사 교정 코퍼스 — 원본/교정 쌍",
        "features": {
            "file_id": {"dtype": "string"},
            "original": {"dtype": "string"},
            "corrected": {"dtype": "string"},
            "language": {"dtype": "string"},
            "tags": {
                "speaker_age": {"dtype": "string"},
                "speaker_gender": {"dtype": "string"},
                "dialect": {"dtype": "string"},
                "topic": {"dtype": "string"},
            },
        },
        "splits": {
            "train": {"num_examples": n_lines},
        },
    }
    (output_dir / "dataset_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info("dataset_exported_hf", path=str(output_dir), entries=n_lines)
    return output_dir
