"""캡션 파싱, 날짜 추출, 파일명 슬러그 생성.

철학: cheroki의 raw 산출물은 self-describing 파일명을 가진다. Short ID는 SQLite
내부 키로만 살아있고, 파일시스템에는 사람이 보자마자 읽을 수 있는 이름이 쌓인다.

한글은 그대로 유지한다(romanize 하지 않는다). 파일시스템 안전성(금지 문자 제거,
공백 처리)만 보장한다.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

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


_UNSAFE_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')
_WS = re.compile(r"\s+")


def safe_slug(text: str) -> str:
    """파일시스템 안전 슬러그. 한글·영문·숫자·대시·점은 유지.

    - 파일시스템 금지 문자(/, \\, :, *, ?, ", <, >, |) 제거
    - 제어 문자 제거
    - 연속 공백 단일화 후 공백을 언더스코어로
    - 앞뒤 언더스코어 정리
    """
    if not text:
        return ""
    cleaned = _UNSAFE_CHARS.sub("", text)
    cleaned = _WS.sub(" ", cleaned).strip()
    return cleaned.replace(" ", "_").strip("_")


def build_slug(
    *,
    caption: str | None,
    original_filename: str | None,
    record_id: str,
    max_length: int = 60,
) -> str:
    """파일명 슬러그 생성. 한글은 그대로 유지.

    우선순위:
    1. 캡션에서 날짜 제거한 나머지
    2. 원본 파일명 (확장자 제외)
    3. short ID (fallback)

    제네릭한 Telegram 기본 파일명(`voice_21`, `audio`, `doc_N`)은 2단계에서 건너뜀.
    """
    candidates: list[str] = []

    if caption:
        stripped = strip_date_from_caption(caption)
        slug = safe_slug(stripped)
        if slug:
            candidates.append(slug)

    if original_filename:
        stem = Path(original_filename).stem
        if not _is_generic_filename(stem):
            slug = safe_slug(stem)
            if slug:
                candidates.append(slug)

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
