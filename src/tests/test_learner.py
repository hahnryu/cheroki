"""지능화 모듈 테스트 — 고유명사 자동 추출, 교정 패턴 학습, vault 연동."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from cheroki.dictionary import Dictionary
from cheroki.learner import (
    extract_proper_nouns_from_corrections,
    auto_update_dictionary,
    learn_correction_patterns,
    suggest_corrections,
    save_patterns,
    load_patterns,
    CorrectionPattern,
    route_to_vault,
)


def _write_corpus(corpus_dir: Path, file_id: str, pairs: list[dict]) -> None:
    """테스트용 코퍼스 파일 생성."""
    data = {
        "file_id": file_id,
        "source_file": f"{file_id}.mp3",
        "language": "ko",
        "created_at": "2026-01-01T00:00:00",
        "pairs": pairs,
    }
    (corpus_dir / f"{file_id}.corpus.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── F3-1: 고유명사 자동 추출 ──────────────────────────

class TestExtractProperNouns:
    def test_basic(self, tmp_path: Path) -> None:
        _write_corpus(tmp_path, "file1", [
            {"original": "김씨가 말했다", "corrected": "김철수가 말했다"},
            {"original": "서울에서", "corrected": "판교에서"},
        ])
        _write_corpus(tmp_path, "file2", [
            {"original": "그 사람이", "corrected": "김철수가"},
        ])
        result = extract_proper_nouns_from_corrections(tmp_path)
        # 한국어 조사가 붙은 형태로 추출됨 ("김철수가")
        assert "김철수가" in result
        assert result["김철수가"] == 2  # 2번 등장

    def test_with_dictionary(self, tmp_path: Path) -> None:
        _write_corpus(tmp_path, "file1", [
            {"original": "그곳에서", "corrected": "판교에서"},
        ])
        d = Dictionary()
        d.add("판교", "places")
        result = extract_proper_nouns_from_corrections(tmp_path, dictionary=d)
        assert "판교" not in result  # 이미 사전에 있으므로 제외

    def test_empty_corpus(self, tmp_path: Path) -> None:
        result = extract_proper_nouns_from_corrections(tmp_path)
        assert result == {}

    def test_english_proper_nouns(self, tmp_path: Path) -> None:
        _write_corpus(tmp_path, "file1", [
            {"original": "the company said", "corrected": "Microsoft said"},
        ])
        result = extract_proper_nouns_from_corrections(tmp_path)
        assert "Microsoft" in result


class TestAutoUpdateDictionary:
    def test_auto_add(self, tmp_path: Path) -> None:
        # 2번 이상 등장해야 추가
        _write_corpus(tmp_path, "file1", [
            {"original": "그가 말했다", "corrected": "류한석이 말했다"},
        ])
        _write_corpus(tmp_path, "file2", [
            {"original": "그 사람이", "corrected": "류한석이"},
        ])
        d = Dictionary()
        added = auto_update_dictionary(tmp_path, d, min_frequency=2)
        assert "류한석이" in added
        assert d.contains("류한석이")

    def test_below_threshold(self, tmp_path: Path) -> None:
        _write_corpus(tmp_path, "file1", [
            {"original": "그가", "corrected": "박영희가"},
        ])
        d = Dictionary()
        added = auto_update_dictionary(tmp_path, d, min_frequency=2)
        assert "박영희" not in added


# ── F3-2: 교정 패턴 학습 ──────────────────────────────

class TestLearnPatterns:
    def test_learn(self, tmp_path: Path) -> None:
        _write_corpus(tmp_path, "file1", [
            {"original": "안녕하세요", "corrected": "안녕하십니까"},
            {"original": "고맙다", "corrected": "감사합니다"},
        ])
        _write_corpus(tmp_path, "file2", [
            {"original": "안녕하세요", "corrected": "안녕하십니까"},
        ])
        patterns = learn_correction_patterns(tmp_path)
        # "안녕하세요→안녕하십니까"가 2번 등장
        top = patterns[0]
        assert top.original == "안녕하세요"
        assert top.corrected == "안녕하십니까"
        assert top.frequency == 2

    def test_empty_corpus(self, tmp_path: Path) -> None:
        patterns = learn_correction_patterns(tmp_path)
        assert patterns == []


class TestSuggestCorrections:
    def test_suggest(self) -> None:
        patterns = [
            CorrectionPattern("잘몬", "잘못", frequency=3),
            CorrectionPattern("됬다", "됐다", frequency=5),
        ]
        suggestions = suggest_corrections("그건 잘몬된 거야", patterns)
        assert len(suggestions) == 1
        assert suggestions[0]["original"] == "잘몬"
        assert suggestions[0]["suggested"] == "잘못"

    def test_no_match(self) -> None:
        patterns = [CorrectionPattern("abc", "def", frequency=1)]
        suggestions = suggest_corrections("아무 관계 없음", patterns)
        assert suggestions == []

    def test_min_frequency(self) -> None:
        patterns = [CorrectionPattern("잘몬", "잘못", frequency=1)]
        suggestions = suggest_corrections("잘몬", patterns, min_frequency=2)
        assert suggestions == []


class TestPatternPersistence:
    def test_save_load(self, tmp_path: Path) -> None:
        patterns = [
            CorrectionPattern("원본1", "교정1", frequency=3, source_files=["f1", "f2"]),
            CorrectionPattern("원본2", "교정2", frequency=1, source_files=["f3"]),
        ]
        path = save_patterns(patterns, tmp_path / "patterns.json")
        loaded = load_patterns(path)
        assert len(loaded) == 2
        assert loaded[0].original == "원본1"
        assert loaded[0].frequency == 3
        assert loaded[1].source_files == ["f3"]


# ── F3-3: Vault 연동 ──────────────────────────────────

class TestRouteToVault:
    def test_route_default(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        log_dir = vault / "20 Log"
        log_dir.mkdir()

        md_file = tmp_path / "test.md"
        md_file.write_text("# Test")

        config = {"paths": {"vault": str(vault), "vault_log": str(log_dir)}}
        dest = route_to_vault(md_file, config)
        assert dest is not None
        assert dest.exists()
        assert dest.parent == log_dir

    def test_route_custom_folder(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()

        md_file = tmp_path / "test.md"
        md_file.write_text("# Test")

        config = {"paths": {"vault": str(vault), "vault_log": str(vault / "20 Log")}}
        dest = route_to_vault(md_file, config, metadata={"vault_folder": "50 Projects"})
        assert dest is not None
        assert "50 Projects" in str(dest)

    def test_vault_not_configured(self, tmp_path: Path) -> None:
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test")
        config = {"paths": {}}
        dest = route_to_vault(md_file, config)
        assert dest is None

    def test_vault_dir_missing(self, tmp_path: Path) -> None:
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test")
        config = {"paths": {"vault": str(tmp_path / "nonexistent")}}
        dest = route_to_vault(md_file, config)
        assert dest is None
