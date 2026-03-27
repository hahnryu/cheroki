"""exporter + metadata 통합 테스트."""

import tempfile
from pathlib import Path

from cheroki.transcriber import Segment, TranscriptionResult
from cheroki.exporter import save_srt, save_markdown
from cheroki.metadata import extract_metadata


def _make_result() -> TranscriptionResult:
    return TranscriptionResult(
        source_file="2026-03-27_interview.wav",
        language="ko",
        language_probability=0.98,
        duration=9.0,
        segments=[
            Segment(start=0.0, end=3.0, text="오늘 인터뷰를 시작합니다", confidence=0.95),
            Segment(start=3.0, end=6.0, text="질문에 답변하겠습니다", confidence=0.9),
            Segment(start=6.0, end=9.0, text="감사합니다", confidence=0.92),
        ],
    )


def test_full_export_with_metadata():
    """메타데이터 추출 → MD 생성 통합 테스트."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        result = _make_result()
        file_id = "20260327_120000_interview"

        meta = extract_metadata(file_id, source_file=result.source_file, full_text=result.full_text)

        srt_path = save_srt(result, tmp, file_id)
        md_path = save_markdown(result, tmp, file_id, metadata=meta)

        assert srt_path.exists()
        assert md_path.exists()

        md_content = md_path.read_text(encoding="utf-8")
        assert "date: 2026-03-27" in md_content
        assert "# interview" in md_content
        assert "[00:00]" in md_content
        assert "오늘 인터뷰를 시작합니다" in md_content

        srt_content = srt_path.read_text(encoding="utf-8")
        assert "오늘 인터뷰를 시작합니다" in srt_content
        assert "-->" in srt_content
