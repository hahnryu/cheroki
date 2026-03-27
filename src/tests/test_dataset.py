"""데이터셋 모듈 테스트 — 패키징, 태깅, 내보내기."""

from __future__ import annotations

import csv
import json
import pytest
from pathlib import Path

from cheroki.dataset import (
    CorpusPackage,
    build_package,
    export_package,
    CorpusTag,
    save_tag,
    load_tag,
    load_all_tags,
    export_jsonl,
    export_csv,
    export_huggingface,
)


def _setup_file(tmp_path: Path, file_id: str = "20260101_000000_test") -> dict:
    """테스트용 파일 구조 생성."""
    dirs = {}
    for d in ["originals", "transcripts", "corrections", "corpus", "exports"]:
        p = tmp_path / d
        p.mkdir()
        dirs[d] = str(p)

    # 원본 메타데이터
    meta = {"file_id": file_id, "stored_path": str(tmp_path / "originals" / f"{file_id}.mp3"), "original_name": "test.mp3"}
    (tmp_path / "originals" / f"{file_id}.meta.json").write_text(json.dumps(meta))
    (tmp_path / "originals" / f"{file_id}.mp3").write_bytes(b"\x00" * 100)

    # 전사 결과
    transcript = {"source_file": "test.mp3", "language": "ko", "segments": [{"text": "안녕", "start": 0, "end": 1, "confidence": 0.9}]}
    (tmp_path / "transcripts" / f"{file_id}.transcript.json").write_text(json.dumps(transcript))
    (tmp_path / "transcripts" / f"{file_id}_final.transcript.json").write_text(json.dumps(transcript))

    # 교정 이력
    corrections = {"file_id": file_id, "corrections": [{"segment_index": 0, "original_text": "안녕", "corrected_text": "안녕하세요"}]}
    (tmp_path / "corrections" / f"{file_id}.corrections.json").write_text(json.dumps(corrections))

    return {"paths": dirs, "whisper": {"model": "tiny"}}


def _write_corpus(corpus_dir: Path, file_id: str, pairs: list[dict]) -> None:
    data = {"file_id": file_id, "language": "ko", "pairs": pairs}
    (corpus_dir / f"{file_id}.corpus.json").write_text(json.dumps(data, ensure_ascii=False))


# ── F5-1: 패키징 ─────────────────────────────────────

class TestBuildPackage:
    def test_build(self, tmp_path: Path) -> None:
        file_id = "20260101_000000_test"
        config = _setup_file(tmp_path, file_id)
        pkg = build_package(file_id, config)
        assert pkg is not None
        assert pkg.file_id == file_id
        assert pkg.original_audio
        assert pkg.raw_transcript
        assert pkg.corrected_transcript
        assert pkg.corrections

    def test_not_found(self, tmp_path: Path) -> None:
        config = {"paths": {"originals": str(tmp_path), "transcripts": str(tmp_path), "corrections": str(tmp_path)}}
        pkg = build_package("nonexistent", config)
        assert pkg is None


class TestExportPackage:
    def test_export(self, tmp_path: Path) -> None:
        file_id = "20260101_000000_test"
        config = _setup_file(tmp_path, file_id)
        pkg = build_package(file_id, config)
        assert pkg is not None

        out_dir = tmp_path / "output"
        pkg_dir = export_package(pkg, out_dir)
        assert pkg_dir.exists()
        assert (pkg_dir / "manifest.json").exists()
        assert (pkg_dir / "audio.mp3").exists()


# ── F5-2: 태깅 ───────────────────────────────────────

class TestCorpusTag:
    def test_save_load(self, tmp_path: Path) -> None:
        tag = CorpusTag(
            file_id="test_001",
            speaker_age="40s",
            speaker_gender="M",
            dialect="표준어",
            topic="기술",
            recording_quality="high",
            duration_seconds=120.5,
            custom={"environment": "studio"},
        )
        path = save_tag(tag, tmp_path)
        loaded = load_tag(path)
        assert loaded.file_id == "test_001"
        assert loaded.speaker_age == "40s"
        assert loaded.dialect == "표준어"
        assert loaded.custom["environment"] == "studio"

    def test_load_all(self, tmp_path: Path) -> None:
        save_tag(CorpusTag(file_id="a", topic="인사"), tmp_path)
        save_tag(CorpusTag(file_id="b", topic="회의"), tmp_path)
        tags = load_all_tags(tmp_path)
        assert len(tags) == 2

    def test_load_empty(self, tmp_path: Path) -> None:
        assert load_all_tags(tmp_path / "nonexistent") == []


# ── F5-3: 데이터셋 내보내기 ──────────────────────────

class TestExportJsonl:
    def test_basic(self, tmp_path: Path) -> None:
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        _write_corpus(corpus_dir, "f1", [
            {"original": "안녕", "corrected": "안녕하세요"},
            {"original": "감사", "corrected": "감사합니다"},
        ])
        out = export_jsonl(corpus_dir, tmp_path / "out.jsonl")
        lines = out.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        entry = json.loads(lines[0])
        assert entry["original"] == "안녕"
        assert entry["corrected"] == "안녕하세요"

    def test_with_tags(self, tmp_path: Path) -> None:
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        tags_dir = tmp_path / "tags"
        tags_dir.mkdir()

        _write_corpus(corpus_dir, "f1", [{"original": "a", "corrected": "b"}])
        save_tag(CorpusTag(file_id="f1", dialect="경상도"), tags_dir)

        out = export_jsonl(corpus_dir, tmp_path / "out.jsonl", tags_dir)
        entry = json.loads(out.read_text(encoding="utf-8").strip())
        assert entry["tags"]["dialect"] == "경상도"

    def test_empty(self, tmp_path: Path) -> None:
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        out = export_jsonl(corpus_dir, tmp_path / "out.jsonl")
        assert out.read_text(encoding="utf-8") == ""


class TestExportCsv:
    def test_basic(self, tmp_path: Path) -> None:
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        _write_corpus(corpus_dir, "f1", [
            {"original": "가", "corrected": "나"},
        ])
        out = export_csv(corpus_dir, tmp_path / "out.csv")
        reader = csv.reader(out.read_text(encoding="utf-8").strip().split("\n"))
        rows = list(reader)
        assert rows[0][0] == "file_id"  # header
        assert rows[1][1] == "가"
        assert rows[1][2] == "나"


class TestExportHuggingface:
    def test_basic(self, tmp_path: Path) -> None:
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        _write_corpus(corpus_dir, "f1", [
            {"original": "x", "corrected": "y"},
        ])
        out_dir = export_huggingface(corpus_dir, tmp_path / "hf_dataset")
        assert (out_dir / "dataset_info.json").exists()
        assert (out_dir / "data" / "train.jsonl").exists()

        info = json.loads((out_dir / "dataset_info.json").read_text(encoding="utf-8"))
        assert info["splits"]["train"]["num_examples"] == 1
