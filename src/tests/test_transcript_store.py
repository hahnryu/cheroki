"""전사 결과 저장/로드 테스트."""

import tempfile
from pathlib import Path

from cheroki.transcriber import Segment, TranscriptionResult
from cheroki.transcript_store import save_transcript, load_transcript


def _sample_result() -> TranscriptionResult:
    return TranscriptionResult(
        source_file="test.wav",
        language="ko",
        language_probability=0.98,
        duration=10.5,
        segments=[
            Segment(start=0.0, end=3.0, text="첫 번째 문장", confidence=0.92),
            Segment(start=3.5, end=7.0, text="두 번째 문장", confidence=0.85),
            Segment(start=7.5, end=10.5, text="세 번째 문장", confidence=0.78),
        ],
    )


def test_save_creates_json_file():
    with tempfile.TemporaryDirectory() as tmp:
        result = _sample_result()
        path = save_transcript(result, Path(tmp), "20260327_120000_test")

        assert path.exists()
        assert path.suffix == ".json"
        assert "20260327_120000_test" in path.name


def test_roundtrip_preserves_data():
    with tempfile.TemporaryDirectory() as tmp:
        original = _sample_result()
        path = save_transcript(original, Path(tmp), "test_roundtrip")
        loaded = load_transcript(path)

        assert loaded.source_file == original.source_file
        assert loaded.language == original.language
        assert loaded.duration == original.duration
        assert len(loaded.segments) == len(original.segments)

        for orig_seg, load_seg in zip(original.segments, loaded.segments):
            assert orig_seg.start == load_seg.start
            assert orig_seg.end == load_seg.end
            assert orig_seg.text == load_seg.text
            assert orig_seg.confidence == load_seg.confidence


def test_full_text_preserved_after_load():
    with tempfile.TemporaryDirectory() as tmp:
        original = _sample_result()
        path = save_transcript(original, Path(tmp), "test_text")
        loaded = load_transcript(path)

        assert loaded.full_text == original.full_text
