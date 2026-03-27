"""export CLI 테스트."""

import tempfile
from pathlib import Path

import yaml
from click.testing import CliRunner

from cheroki.cli import main
from cheroki.transcriber import Segment, TranscriptionResult
from cheroki.transcript_store import save_transcript


def _setup_env(tmp: Path) -> tuple[Path, str]:
    """테스트 환경 구성."""
    transcripts = tmp / "transcripts"
    exports = tmp / "exports"

    config_path = tmp / "config.yaml"
    config_path.write_text(yaml.dump({
        "paths": {
            "originals": str(tmp / "originals"),
            "transcripts": str(transcripts),
            "corrections": str(tmp / "corrections"),
            "corpus": str(tmp / "corpus"),
            "exports": str(exports),
        },
        "whisper": {"model": "medium", "language": "ko", "device": "cpu", "compute_type": "int8"},
        "transcription": {"min_confidence": 0.7, "chunk_length": 30},
    }), encoding="utf-8")

    result = TranscriptionResult(
        source_file="2026-03-27_interview.wav",
        language="ko",
        language_probability=0.98,
        duration=9.0,
        segments=[
            Segment(start=0.0, end=3.0, text="첫 번째 문장", confidence=0.95),
            Segment(start=3.0, end=6.0, text="두 번째 문장", confidence=0.9),
            Segment(start=6.0, end=9.0, text="세 번째 문장", confidence=0.88),
        ],
    )
    file_id = "20260327_120000_interview"
    save_transcript(result, transcripts, file_id)

    return config_path, file_id


def test_export_creates_srt_and_md():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config_path, file_id = _setup_env(tmp)

        runner = CliRunner()
        result = runner.invoke(main, ["export", file_id, "--config", str(config_path)])

        assert result.exit_code == 0
        assert "산출물 생성 완료" in result.output

        exports = tmp / "exports"
        assert (exports / f"{file_id}.srt").exists()
        assert (exports / f"{file_id}.md").exists()


def test_export_srt_content():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config_path, file_id = _setup_env(tmp)

        runner = CliRunner()
        runner.invoke(main, ["export", file_id, "--config", str(config_path)])

        srt = (tmp / "exports" / f"{file_id}.srt").read_text(encoding="utf-8")
        assert "-->" in srt
        assert "첫 번째 문장" in srt


def test_export_md_content():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config_path, file_id = _setup_env(tmp)

        runner = CliRunner()
        runner.invoke(main, ["export", file_id, "--config", str(config_path)])

        md = (tmp / "exports" / f"{file_id}.md").read_text(encoding="utf-8")
        assert "---" in md
        assert "date: 2026-03-27" in md
        assert "첫 번째 문장" in md


def test_export_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config_path, _ = _setup_env(tmp)

        runner = CliRunner()
        result = runner.invoke(main, ["export", "nonexistent", "--config", str(config_path)])
        assert result.exit_code != 0


def test_export_prefers_final():
    """최종본이 있으면 최종본을 사용."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config_path, file_id = _setup_env(tmp)
        transcripts = tmp / "transcripts"

        # 최종본 생성 (교정된 텍스트)
        final_result = TranscriptionResult(
            source_file="2026-03-27_interview.wav",
            language="ko",
            language_probability=0.98,
            duration=9.0,
            segments=[
                Segment(start=0.0, end=3.0, text="교정된 첫 문장", confidence=1.0),
                Segment(start=3.0, end=6.0, text="두 번째 문장", confidence=0.9),
                Segment(start=6.0, end=9.0, text="세 번째 문장", confidence=0.88),
            ],
        )
        save_transcript(final_result, transcripts, f"{file_id}_final")

        runner = CliRunner()
        runner.invoke(main, ["export", file_id, "--config", str(config_path)])

        md = (tmp / "exports" / f"{file_id}.md").read_text(encoding="utf-8")
        assert "교정된 첫 문장" in md
