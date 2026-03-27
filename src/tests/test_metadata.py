"""metadata 모듈 테스트."""

from cheroki.metadata import extract_date_from_filename, extract_date_from_text, extract_metadata


def test_date_from_filename_dash():
    assert extract_date_from_filename("2026-03-27_interview.wav") == "2026-03-27"


def test_date_from_filename_compact():
    assert extract_date_from_filename("20260327_recording.mp3") == "2026-03-27"


def test_date_from_filename_underscore():
    assert extract_date_from_filename("2026_03_27_meeting.m4a") == "2026-03-27"


def test_date_from_filename_none():
    assert extract_date_from_filename("random_file.wav") is None


def test_date_from_text_korean():
    assert extract_date_from_text("오늘은 2026년 3월 27일입니다") == "2026-03-27"


def test_date_from_text_numeric():
    assert extract_date_from_text("녹음일: 20260327") == "2026-03-27"


def test_date_from_text_none():
    assert extract_date_from_text("날짜 없는 텍스트입니다") is None


def test_extract_metadata_with_date():
    meta = extract_metadata(
        file_id="20260327_120000_interview",
        source_file="2026-03-27_interview.wav",
    )
    assert meta["date"] == "2026-03-27"
    assert meta["title"] == "interview"


def test_extract_metadata_title_from_file_id():
    meta = extract_metadata(file_id="20260327_120000_my_recording")
    assert meta["title"] == "my recording"


def test_extract_metadata_fallback_title():
    meta = extract_metadata(file_id="simple")
    assert meta["title"] == "simple"
