"""교정 루프 CLI 테스트."""

import json
import tempfile
from pathlib import Path

import yaml
from click.testing import CliRunner

from cheroki.cli import main
from cheroki.transcriber import Segment, TranscriptionResult
from cheroki.transcript_store import save_transcript


def _setup_env(tmp: Path) -> tuple[Path, str]:
    """테스트 환경 구성: config + 전사 결과."""
    transcripts = tmp / "transcripts"
    corrections = tmp / "corrections"
    corpus = tmp / "corpus"

    config_path = tmp / "config.yaml"
    config_path.write_text(yaml.dump({
        "paths": {
            "originals": str(tmp / "originals"),
            "transcripts": str(transcripts),
            "corrections": str(corrections),
            "corpus": str(corpus),
            "exports": str(tmp / "exports"),
        },
        "whisper": {"model": "medium", "language": "ko", "device": "cpu", "compute_type": "int8"},
        "transcription": {"min_confidence": 0.7, "chunk_length": 30},
    }), encoding="utf-8")

    result = TranscriptionResult(
        source_file="test.wav",
        language="ko",
        language_probability=0.98,
        duration=9.0,
        segments=[
            Segment(start=0.0, end=3.0, text="정상 문장입니다", confidence=0.95),
            Segment(start=3.0, end=6.0, text="의심스러운 문장", confidence=0.4),
            Segment(start=6.0, end=9.0, text="마지막 문장", confidence=0.9),
        ],
    )
    file_id = "test_review"
    save_transcript(result, transcripts, file_id)

    return config_path, file_id


def test_review_command():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config_path, file_id = _setup_env(tmp)

        runner = CliRunner()
        result = runner.invoke(main, ["review", file_id, "--config", str(config_path)])
        assert result.exit_code == 0
        assert "의심 구간" in result.output
        assert "00:03-00:06" in result.output


def test_review_no_suspicious():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        transcripts = tmp / "transcripts"

        config_path = tmp / "config.yaml"
        config_path.write_text(yaml.dump({
            "paths": {
                "originals": str(tmp / "originals"),
                "transcripts": str(transcripts),
                "corrections": str(tmp / "corrections"),
                "corpus": str(tmp / "corpus"),
                "exports": str(tmp / "exports"),
            },
            "whisper": {"model": "medium", "language": "ko", "device": "cpu", "compute_type": "int8"},
            "transcription": {"min_confidence": 0.7, "chunk_length": 30},
        }), encoding="utf-8")

        result = TranscriptionResult(
            source_file="test.wav", language="ko",
            language_probability=0.98, duration=3.0,
            segments=[Segment(start=0.0, end=3.0, text="완벽한 문장", confidence=0.99)],
        )
        save_transcript(result, transcripts, "perfect")

        runner = CliRunner()
        res = runner.invoke(main, ["review", "perfect", "--config", str(config_path)])
        assert res.exit_code == 0
        assert "양호" in res.output


def test_correct_command():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config_path, file_id = _setup_env(tmp)

        # 교정 파일 생성
        corrections_file = tmp / "my_corrections.json"
        corrections_file.write_text(json.dumps([
            {"segment_index": 1, "corrected_text": "교정된 문장"},
        ], ensure_ascii=False), encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(main, [
            "correct", file_id, str(corrections_file), "--config", str(config_path),
        ])
        assert result.exit_code == 0
        assert "교정 완료" in result.output
        assert "1개 세그먼트" in result.output

        # 최종본 확인
        final = tmp / "transcripts" / f"{file_id}_final.transcript.json"
        assert final.exists()

        # 교정 이력 확인
        corr = tmp / "corrections" / f"{file_id}.corrections.json"
        assert corr.exists()

        # 코퍼스 확인
        corpus_files = list((tmp / "corpus").glob("*.corpus.json"))
        assert len(corpus_files) == 1
