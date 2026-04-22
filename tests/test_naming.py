from __future__ import annotations

from datetime import date, datetime

from cheroki.naming import (
    build_slug,
    file_format_from_name,
    parse_recording_date,
    safe_slug,
    session_folder_name,
    strip_date_from_caption,
)


def test_safe_slug_keeps_korean():
    assert safe_slug("아버님 morning walk") == "아버님_morning_walk"


def test_safe_slug_empty():
    assert safe_slug("") == ""
    assert safe_slug("   ") == ""


def test_safe_slug_removes_filesystem_unsafe_chars():
    assert safe_slug("파일/이름") == "파일이름"
    assert safe_slug('a:b*c?d"e<f>g|h') == "abcdefgh"


def test_safe_slug_collapses_whitespace():
    assert safe_slug("하회  마을    보존회") == "하회_마을_보존회"


def test_safe_slug_preserves_case_and_punct():
    # 대소문자 유지, 콤마·점·대시 유지
    assert safe_slug("HAHOE Village, 2026.04") == "HAHOE_Village,_2026.04"


def test_parse_date_yymmdd():
    d = parse_recording_date("morning walk 260420 하회")
    assert d == date(2026, 4, 20)


def test_parse_date_yyyy_mm_dd():
    d = parse_recording_date("아버님 구술 2026-04-20 부용대")
    assert d == date(2026, 4, 20)


def test_parse_date_dotted():
    d = parse_recording_date("2026.04.20 morning")
    assert d == date(2026, 4, 20)


def test_parse_date_fallback():
    fb = datetime(2026, 3, 15)
    assert parse_recording_date("no date here", fallback=fb) == date(2026, 3, 15)


def test_parse_date_none_returns_today():
    from datetime import date as _date
    result = parse_recording_date(None, fallback=None)
    assert result == _date.today()


def test_strip_date_from_caption():
    assert strip_date_from_caption("morning walk 260420 하회") == "morning walk 하회"
    assert strip_date_from_caption("2026-04-20 · 구술사") == "구술사"


def test_build_slug_from_caption():
    slug = build_slug(caption="아버님 morning walk 260420 하회", original_filename=None, record_id="ab7f3c")
    assert "아버님" in slug
    assert "morning_walk" in slug
    assert "하회" in slug
    assert "260420" not in slug  # 날짜는 폴더로 빠짐


def test_build_slug_fallback_to_filename():
    slug = build_slug(caption=None, original_filename="interview_aboji.m4a", record_id="ab7f3c")
    assert slug == "interview_aboji"


def test_build_slug_skips_generic_filename():
    # Telegram 자동 명명(voice_21)은 무시하고 record_id로 폴백
    slug = build_slug(caption=None, original_filename="voice_21.ogg", record_id="ab7f3c")
    assert slug == "ab7f3c"


def test_build_slug_fallback_to_record_id():
    slug = build_slug(caption=None, original_filename=None, record_id="xy9k23")
    assert slug == "xy9k23"


def test_build_slug_length_cap():
    long = "가" * 100
    slug = build_slug(caption=long, original_filename=None, record_id="ab7f3c", max_length=60)
    assert len(slug) <= 60


def test_session_folder_name():
    assert session_folder_name(date(2026, 4, 20)) == "260420"
    assert session_folder_name(date(2099, 12, 31)) == "991231"


def test_file_format_from_name():
    assert file_format_from_name("foo.M4A") == ".m4a"
    assert file_format_from_name("bar.mp3") == ".mp3"
    assert file_format_from_name(None) == ""
    assert file_format_from_name("no_ext") == ""
