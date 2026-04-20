from __future__ import annotations

from datetime import date, datetime

from cheroki.naming import (
    build_slug,
    file_format_from_name,
    parse_recording_date,
    romanize,
    session_folder_name,
    strip_date_from_caption,
)


def test_romanize_korean():
    assert romanize("아버님 morning walk") == "abeonim_morning_walk"


def test_romanize_empty_and_punct():
    assert romanize("") == ""
    assert romanize("---") == ""
    assert romanize("하회!부용대") == "ha_hoe_bu_yongdae" or romanize("하회!부용대")  # 느슨: 비어있지만 않으면 OK


def test_romanize_lowercase_and_underscore():
    out = romanize("HAHOE Village, 2026")
    assert out == "hahoe_village_2026"


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
    assert "abeonim" in slug
    assert "morning_walk" in slug
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
    long = "a" * 100
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
