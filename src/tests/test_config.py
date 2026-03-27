"""config 모듈 테스트."""

import tempfile
from pathlib import Path

import yaml

from cheroki.config import load_config, ensure_directories, get_config


def _write_config(tmp: Path) -> Path:
    config_path = tmp / "config.yaml"
    config_path.write_text(
        yaml.dump({
            "paths": {
                "originals": str(tmp / "originals"),
                "transcripts": str(tmp / "transcripts"),
                "corrections": str(tmp / "corrections"),
                "corpus": str(tmp / "corpus"),
                "exports": str(tmp / "exports"),
                "vault": "",
            },
            "whisper": {
                "model": "medium",
                "language": "ko",
                "device": "cpu",
                "compute_type": "int8",
            },
            "transcription": {
                "min_confidence": 0.7,
                "chunk_length": 30,
            },
        }),
        encoding="utf-8",
    )
    return config_path


def test_load_config_returns_all_sections():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = _write_config(Path(tmp))
        config = load_config(config_path)

        assert "paths" in config
        assert "whisper" in config
        assert "transcription" in config
        assert config["whisper"]["model"] == "medium"
        assert config["whisper"]["language"] == "ko"


def test_ensure_directories_creates_folders():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = _write_config(Path(tmp))
        config = load_config(config_path)
        ensure_directories(config)

        for key in ["originals", "transcripts", "corrections", "corpus", "exports"]:
            assert Path(config["paths"][key]).is_dir()


def test_get_config_loads_and_creates():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = _write_config(Path(tmp))
        config = get_config(config_path)

        assert config["whisper"]["compute_type"] == "int8"
        assert Path(config["paths"]["originals"]).is_dir()


def test_tilde_expansion():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "config.yaml"
        config_path.write_text(
            yaml.dump({
                "paths": {
                    "originals": "~/test-cheroki-originals",
                    "transcripts": str(Path(tmp) / "transcripts"),
                    "corrections": str(Path(tmp) / "corrections"),
                    "corpus": str(Path(tmp) / "corpus"),
                    "exports": str(Path(tmp) / "exports"),
                },
                "whisper": {"model": "medium", "language": "ko", "device": "cpu", "compute_type": "int8"},
                "transcription": {"min_confidence": 0.7, "chunk_length": 30},
            }),
            encoding="utf-8",
        )
        config = load_config(config_path)
        assert "~" not in config["paths"]["originals"]
        assert Path(config["paths"]["originals"]).is_absolute()
