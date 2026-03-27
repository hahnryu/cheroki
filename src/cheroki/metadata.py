"""메타데이터 자동 추출 모듈."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any


# 날짜 패턴들
_DATE_PATTERNS = [
    # 파일명: 20260327, 2026-03-27, 2026_03_27
    (re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})"), "%Y%m%d"),
    # 텍스트: 2026년 3월 27일
    (re.compile(r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일"), None),
]

# 장소 키워드 (텍스트에서 추출)
_PLACE_PATTERN = re.compile(
    r"(?:에서|에서의|에서는|장소[는은]?)\s*(.{2,20}?)(?:[에서으로이가]|[,.]|\s*$)"
)

# 참가자 패턴 (한국 이름: 2~4글자)
_KOREAN_NAME_PATTERN = re.compile(r"[가-힣]{2,4}")


def extract_date_from_filename(filename: str) -> str | None:
    """파일명에서 날짜를 추출한다. ISO 형식 반환."""
    for pattern, _ in _DATE_PATTERNS:
        m = pattern.search(filename)
        if m:
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dt = datetime(y, mo, d)
                return dt.strftime("%Y-%m-%d")
            except (ValueError, IndexError):
                continue
    return None


def extract_date_from_text(text: str) -> str | None:
    """전사 텍스트에서 날짜를 추출한다."""
    for pattern, _ in _DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dt = datetime(y, mo, d)
                return dt.strftime("%Y-%m-%d")
            except (ValueError, IndexError):
                continue
    return None


def extract_metadata(
    file_id: str,
    source_file: str = "",
    full_text: str = "",
) -> dict[str, Any]:
    """파일명과 전사 텍스트에서 메타데이터를 자동 추출한다.

    Returns:
        {date, place, participants, tags, title}
    """
    meta: dict[str, Any] = {}

    # 날짜: 파일명 우선, 없으면 텍스트
    date = extract_date_from_filename(source_file or file_id)
    if not date:
        date = extract_date_from_text(full_text)
    if date:
        meta["date"] = date

    # 제목: file_id에서 타임스탬프 제거한 부분
    # file_id 형식: YYYYMMDD_HHMMSS_원래파일명
    parts = file_id.split("_", 2)
    if len(parts) >= 3:
        meta["title"] = parts[2].replace("_", " ")
    else:
        meta["title"] = file_id

    return meta
