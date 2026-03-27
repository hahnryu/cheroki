"""산출물 생성 모듈 — SRT, MD."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cheroki.transcriber import TranscriptionResult, Segment


# ── SRT ──────────────────────────────────────────────

def _srt_timestamp(seconds: float) -> str:
    """초를 SRT 타임스탬프 형식으로: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_srt(result: TranscriptionResult) -> str:
    """TranscriptionResult를 SRT 문자열로 변환."""
    lines: list[str] = []
    for i, seg in enumerate(result.segments, 1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(seg.start)} --> {_srt_timestamp(seg.end)}")
        lines.append(seg.text.strip())
        lines.append("")
    return "\n".join(lines)


def save_srt(result: TranscriptionResult, exports_dir: Path, file_id: str) -> Path:
    """SRT 파일을 저장."""
    exports_dir = Path(exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)
    out_path = exports_dir / f"{file_id}.srt"
    out_path.write_text(generate_srt(result), encoding="utf-8")
    return out_path


# ── Markdown ─────────────────────────────────────────

def _time_label(seconds: float) -> str:
    """MM:SS 형식."""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def generate_markdown(
    result: TranscriptionResult,
    file_id: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    """TranscriptionResult를 Markdown 문자열로 변환.

    Args:
        result: 전사 결과
        file_id: 파일 ID
        metadata: YAML frontmatter에 포함할 메타데이터
    """
    parts: list[str] = []

    # YAML frontmatter
    meta = metadata or {}
    parts.append("---")
    parts.append(f"file_id: {file_id}")
    parts.append(f"source: {result.source_file}")
    parts.append(f"language: {result.language}")
    parts.append(f"duration: {result.duration}")
    if meta.get("date"):
        parts.append(f"date: {meta['date']}")
    if meta.get("place"):
        parts.append(f"place: {meta['place']}")
    if meta.get("participants"):
        participants = meta["participants"]
        if isinstance(participants, list):
            parts.append("participants:")
            for p in participants:
                parts.append(f"  - {p}")
        else:
            parts.append(f"participants: {participants}")
    if meta.get("tags"):
        tags = meta["tags"]
        if isinstance(tags, list):
            parts.append("tags:")
            for t in tags:
                parts.append(f"  - {t}")
        else:
            parts.append(f"tags: {tags}")
    parts.append("---")
    parts.append("")

    # 제목
    title = meta.get("title", file_id)
    parts.append(f"# {title}")
    parts.append("")

    # 세그먼트
    for seg in result.segments:
        speaker = getattr(seg, "speaker", None) or ""
        time_str = _time_label(seg.start)
        if speaker:
            parts.append(f"**[{time_str}] {speaker}:** {seg.text.strip()}")
        else:
            parts.append(f"**[{time_str}]** {seg.text.strip()}")
        parts.append("")

    return "\n".join(parts)


def save_markdown(
    result: TranscriptionResult,
    exports_dir: Path,
    file_id: str,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Markdown 파일을 저장."""
    exports_dir = Path(exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)
    out_path = exports_dir / f"{file_id}.md"
    out_path.write_text(
        generate_markdown(result, file_id, metadata),
        encoding="utf-8",
    )
    return out_path
