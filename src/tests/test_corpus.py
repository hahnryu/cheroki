"""corpus 모듈 테스트."""

import tempfile
from pathlib import Path

from cheroki.corrector import Correction
from cheroki.corpus import (
    save_corpus_pairs,
    load_corpus_pairs,
    count_corpus_pairs,
    list_corpus_files,
)


def test_save_corpus_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        corrections = [
            Correction(segment_index=0, original_text="틀림", corrected_text="맞음"),
            Correction(segment_index=1, original_text="또틀림", corrected_text="또맞음"),
        ]
        path = save_corpus_pairs("test_id", corrections, tmp)
        assert path.exists()
        assert path.suffix == ".json"


def test_save_corpus_skips_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        corrections = [
            Correction(segment_index=0, original_text="같은텍스트", corrected_text="같은텍스트"),
        ]
        path = save_corpus_pairs("test_id", corrections, tmp)
        # 변경 없으면 파일 생성 안 함, 디렉토리 반환
        assert path == tmp


def test_load_corpus_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        corrections = [
            Correction(segment_index=0, original_text="원본", corrected_text="교정"),
        ]
        path = save_corpus_pairs("roundtrip", corrections, tmp, source_file="test.wav")
        data = load_corpus_pairs(path)

        assert data["file_id"] == "roundtrip"
        assert data["source_file"] == "test.wav"
        assert len(data["pairs"]) == 1
        assert data["pairs"][0]["original"] == "원본"
        assert data["pairs"][0]["corrected"] == "교정"


def test_count_corpus_pairs():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # 파일 1: 2쌍
        save_corpus_pairs("file1", [
            Correction(segment_index=0, original_text="a", corrected_text="b"),
            Correction(segment_index=1, original_text="c", corrected_text="d"),
        ], tmp)

        # 파일 2: 1쌍
        save_corpus_pairs("file2", [
            Correction(segment_index=0, original_text="e", corrected_text="f"),
        ], tmp)

        assert count_corpus_pairs(tmp) == 3


def test_list_corpus_files():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        save_corpus_pairs("alpha", [
            Correction(segment_index=0, original_text="a", corrected_text="b"),
        ], tmp)
        save_corpus_pairs("beta", [
            Correction(segment_index=0, original_text="c", corrected_text="d"),
        ], tmp)

        files = list_corpus_files(tmp)
        assert len(files) == 2
