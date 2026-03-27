"""exporter 모듈 테스트."""

import tempfile
from pathlib import Path

from cheroki.transcriber import Segment, TranscriptionResult
from cheroki.exporter import generate_srt, save_srt, generate_markdown, save_markdown


def _make_result() -> TranscriptionResult:
    return TranscriptionResult(
        source_file="interview.wav",
        language="ko",
        language_probability=0.98,
        duration=12.5,
        segments=[
            Segment(start=0.0, end=3.5, text="첫 번째 문장입니다", confidence=0.95),
            Segment(start=3.5, end=7.0, text="두 번째 문장입니다", confidence=0.9),
            Segment(start=7.0, end=12.5, text="세 번째 문장입니다", confidence=0.88),
        ],
    )


# ── SRT 테스트 ──

def test_srt_format():
    srt = generate_srt(_make_result())
    lines = srt.strip().split("\n")

    # 첫 번째 자막 블록
    assert lines[0] == "1"
    assert "-->" in lines[1]
    assert "00:00:00,000 --> 00:00:03,500" == lines[1]
    assert lines[2] == "첫 번째 문장입니다"


def test_srt_numbering():
    srt = generate_srt(_make_result())
    # 3개 세그먼트 → 1, 2, 3
    assert "\n1\n" in srt or srt.startswith("1\n")
    assert "\n2\n" in srt
    assert "\n3\n" in srt


def test_srt_timestamp_format():
    srt = generate_srt(_make_result())
    # HH:MM:SS,mmm 형식 확인
    assert "00:00:03,500 --> 00:00:07,000" in srt


def test_save_srt():
    with tempfile.TemporaryDirectory() as tmp:
        path = save_srt(_make_result(), Path(tmp), "test_export")
        assert path.exists()
        assert path.suffix == ".srt"
        content = path.read_text(encoding="utf-8")
        assert "첫 번째 문장입니다" in content


# ── Markdown 테스트 ──

def test_markdown_has_frontmatter():
    md = generate_markdown(_make_result(), "test_id")
    assert md.startswith("---")
    assert "file_id: test_id" in md
    assert "language: ko" in md
    assert "duration: 12.5" in md


def test_markdown_has_timestamps():
    md = generate_markdown(_make_result(), "test_id")
    assert "[00:00]" in md
    assert "[00:03]" in md
    assert "[00:07]" in md


def test_markdown_with_metadata():
    meta = {
        "date": "2026-03-27",
        "place": "서울",
        "participants": ["류한석", "김철수"],
        "tags": ["인터뷰", "기록"],
        "title": "테스트 인터뷰",
    }
    md = generate_markdown(_make_result(), "test_id", metadata=meta)
    assert "date: 2026-03-27" in md
    assert "place: 서울" in md
    assert "  - 류한석" in md
    assert "  - 인터뷰" in md
    assert "# 테스트 인터뷰" in md


def test_save_markdown():
    with tempfile.TemporaryDirectory() as tmp:
        path = save_markdown(_make_result(), Path(tmp), "test_md")
        assert path.exists()
        assert path.suffix == ".md"
        content = path.read_text(encoding="utf-8")
        assert "첫 번째 문장입니다" in content
        assert "---" in content
