"""diarizer 모듈 테스트."""

from cheroki.transcriber import Segment, TranscriptionResult
from cheroki.diarizer import SpeakerSegment, assign_speakers, _find_speaker, diarize
from cheroki.exporter import generate_markdown


def _make_result() -> TranscriptionResult:
    return TranscriptionResult(
        source_file="test.wav",
        language="ko",
        language_probability=0.98,
        duration=12.0,
        segments=[
            Segment(start=0.0, end=3.0, text="안녕하세요 저는 A입니다", confidence=0.95),
            Segment(start=3.0, end=6.0, text="네 반갑습니다 B입니다", confidence=0.9),
            Segment(start=6.0, end=9.0, text="오늘 주제는 무엇인가요", confidence=0.88),
            Segment(start=9.0, end=12.0, text="네 시작하겠습니다", confidence=0.92),
        ],
    )


def test_find_speaker():
    segments = [
        SpeakerSegment(speaker="SPEAKER_00", start=0.0, end=5.0),
        SpeakerSegment(speaker="SPEAKER_01", start=5.0, end=10.0),
    ]
    assert _find_speaker(2.5, segments) == "SPEAKER_00"
    assert _find_speaker(7.5, segments) == "SPEAKER_01"
    assert _find_speaker(99.0, segments) == "UNKNOWN"


def test_assign_speakers():
    result = _make_result()
    speaker_segs = [
        SpeakerSegment(speaker="화자A", start=0.0, end=4.0),
        SpeakerSegment(speaker="화자B", start=4.0, end=8.0),
        SpeakerSegment(speaker="화자A", start=8.0, end=12.0),
    ]
    labeled = assign_speakers(result, speaker_segs)

    assert len(labeled.segments) == 4
    # 세그먼트 중간점 기준: 1.5→A, 4.5→B, 7.5→B, 10.5→A
    assert getattr(labeled.segments[0], "speaker") == "화자A"
    assert getattr(labeled.segments[1], "speaker") == "화자B"
    assert getattr(labeled.segments[2], "speaker") == "화자B"
    assert getattr(labeled.segments[3], "speaker") == "화자A"


def test_assign_speakers_preserves_text():
    result = _make_result()
    speaker_segs = [SpeakerSegment(speaker="X", start=0.0, end=12.0)]
    labeled = assign_speakers(result, speaker_segs)

    for orig, new in zip(result.segments, labeled.segments):
        assert orig.text == new.text
        assert orig.confidence == new.confidence


def test_empty_speaker_segments():
    result = _make_result()
    labeled = assign_speakers(result, [])

    for seg in labeled.segments:
        assert getattr(seg, "speaker") == "UNKNOWN"


def test_diarize_without_pyannote():
    """pyannote 미설치 시 빈 리스트 반환."""
    from pathlib import Path
    segments = diarize(Path("/nonexistent.wav"))
    assert segments == []


def test_markdown_with_speakers():
    """화자 라벨이 MD 출력에 반영되는지 확인."""
    result = _make_result()
    speaker_segs = [
        SpeakerSegment(speaker="류한석", start=0.0, end=6.0),
        SpeakerSegment(speaker="김철수", start=6.0, end=12.0),
    ]
    labeled = assign_speakers(result, speaker_segs)
    md = generate_markdown(labeled, "test_speakers")

    assert "류한석" in md
    assert "김철수" in md
