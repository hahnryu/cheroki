"""storage 모듈 테스트."""

import tempfile
from pathlib import Path

import pytest

from cheroki.storage import store_original, load_metadata, file_hash, is_audio_file


def _create_fake_audio(tmp: Path, name: str = "test.wav") -> Path:
    """테스트용 가짜 음성 파일 생성."""
    audio_path = tmp / name
    audio_path.write_bytes(b"RIFF" + b"\x00" * 1000)  # 가짜 WAV 헤더
    return audio_path


def test_is_audio_file():
    assert is_audio_file(Path("test.wav"))
    assert is_audio_file(Path("test.MP3"))
    assert is_audio_file(Path("test.m4a"))
    assert not is_audio_file(Path("test.txt"))
    assert not is_audio_file(Path("test.py"))


def test_store_original_copies_file():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        source = _create_fake_audio(tmp)
        originals_dir = tmp / "originals"

        metadata = store_original(source, originals_dir)

        assert metadata["original_name"] == "test.wav"
        assert Path(metadata["stored_path"]).is_file()
        assert metadata["sha256"] == file_hash(source)
        assert metadata["size_bytes"] == source.stat().st_size


def test_store_original_creates_metadata_json():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        source = _create_fake_audio(tmp)
        originals_dir = tmp / "originals"

        metadata = store_original(source, originals_dir)

        meta_files = list(originals_dir.glob("*.meta.json"))
        assert len(meta_files) == 1

        loaded = load_metadata(meta_files[0])
        assert loaded["file_id"] == metadata["file_id"]
        assert loaded["sha256"] == metadata["sha256"]


def test_store_original_hash_integrity():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        source = _create_fake_audio(tmp)
        originals_dir = tmp / "originals"

        metadata = store_original(source, originals_dir)

        stored = Path(metadata["stored_path"])
        assert file_hash(source) == file_hash(stored)


def test_store_original_rejects_non_audio():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        text_file = tmp / "notes.txt"
        text_file.write_text("hello")

        with pytest.raises(ValueError, match="지원하지 않는 형식"):
            store_original(text_file, tmp / "originals")


def test_store_original_rejects_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        with pytest.raises(FileNotFoundError):
            store_original(tmp / "nonexistent.wav", tmp / "originals")
