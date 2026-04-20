"""캡션 파싱, 날짜 추출, romanize, 파일명 슬러그 생성.

철학: cheroki의 raw 산출물은 self-describing 파일명을 가진다. Short ID는 SQLite
내부 키로만 살아있고, 파일시스템에는 사람이 보자마자 읽을 수 있는 이름이 쌓인다.

이후 교정/이름지정 모듈들이 이 폴더 구조 위에서 작동할 것이므로, 네이밍 규약을
가능한 한 단순·안정적으로 유지한다.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from unidecode import unidecode

_DATE_PATTERNS = [
    # 2026-04-20, 2026.04.20, 2026/04/20, 2026 04 20
    re.compile(r"(?<!\d)(20\d{2})[-./\s](\d{1,2})[-./\s](\d{1,2})(?!\d)"),
    # 260420, 26-04-20, 26.04.20, 26/04/20
    re.compile(r"(?<!\d)(\d{2})[-./](\d{2})[-./](\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)"),
]


def parse_recording_date(
    caption: str | None, *, fallback: datetime | date | None = None
) -> date:
    """캡션에서 녹음 날짜 추출. 실패 시 fallback (없으면 today)."""
    if caption:
        for pat in _DATE_PATTERNS:
            m = pat.search(caption)
            if not m:
                continue
            y, mo, d = m.group(1), m.group(2), m.group(3)
            try:
                year = int(y)
                if year < 100:
                    year += 2000
                return date(year, int(mo), int(d))
            except ValueError:
                continue

    if fallback is None:
        return date.today()
    if isinstance(fallback, datetime):
        return fallback.date()
    return fallback


def strip_date_from_caption(caption: str) -> str:
    """캡션에서 날짜 표현을 제거하고 남는 부분을 반환."""
    result = caption
    for pat in _DATE_PATTERNS:
        result = pat.sub(" ", result)
    return re.sub(r"\s+", " ", result).strip(" ·,-_/")


def romanize(text: str) -> str:
    """한글·기타 유니코드 → ASCII 슬러그. 소문자, 단어 구분은 `_`."""
    if not text:
        return ""
    ascii_text = unidecode(text)
    ascii_text = ascii_text.lower()
    # 영숫자와 몇몇 구분문자만 남기고 공백으로
    ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    # 연속 공백 → 단일 `_`
    slug = "_".join(ascii_text.split())
    return slug.strip("_")


def build_slug(
    *,
    caption: str | None,
    original_filename: str | None,
    record_id: str,
    max_length: int = 60,
) -> str:
    """파일명 슬러그 생성.

    우선순위:
    1. 캡션에서 날짜 제거한 나머지 (romanize)
    2. 원본 파일명 (확장자 제외, romanize)
    3. short ID (fallback)

    제네릭한 Telegram 기본 파일명(`voice_21`, `audio`, `doc_N`)은 2단계에서 건너뜀.
    """
    candidates: list[str] = []

    if caption:
        stripped = strip_date_from_caption(caption)
        rom = romanize(stripped)
        if rom:
            candidates.append(rom)

    if original_filename:
        stem = Path(original_filename).stem
        if not _is_generic_filename(stem):
            rom = romanize(stem)
            if rom:
                candidates.append(rom)

    candidates.append(record_id)

    slug = candidates[0]
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip("_")
    return slug


def _is_generic_filename(stem: str) -> bool:
    """`voice_21`, `audio`, `doc_5`, `videonote_3` 같은 Telegram 자동 명명 판별."""
    s = stem.lower()
    return bool(
        re.fullmatch(r"(voice|audio|video|videonote|doc|file|recording)(_\d+)?", s)
    )


def session_folder_name(d: date) -> str:
    """폴더명 YYMMDD (예: 260420)."""
    return d.strftime("%y%m%d")


def file_format_from_name(filename: str | None) -> str:
    """원본 파일 확장자 (소문자, 점 포함). 없으면 빈 문자열."""
    if not filename:
        return ""
    return Path(filename).suffix.lower()
