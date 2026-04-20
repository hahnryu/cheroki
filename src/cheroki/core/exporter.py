"""TranscriptionResult -> SRT / Markdown / TXT 변환."""
from __future__ import annotations

from datetime import UTC, datetime

from cheroki.core.types import TranscriptionMetadata, Utterance


def to_srt(utterances: list[Utterance]) -> str:
    """SRT 자막 포맷. 화자는 `S0:` 접두어로 표시."""
    blocks: list[str] = []
    for idx, u in enumerate(utterances, start=1):
        blocks.append(
            f"{idx}\n"
            f"{_srt_ts(u.start)} --> {_srt_ts(u.end)}\n"
            f"S{u.speaker}: {u.text}\n"
        )
    return "\n".join(blocks)


def to_markdown(
    utterances: list[Utterance],
    metadata: TranscriptionMetadata,
    *,
    title: str | None = None,
) -> str:
    created = datetime.now(UTC).isoformat(timespec="seconds")
    front = [
        "---",
        f"title: {title or '녹취'}",
        f"duration: {_hms(metadata.duration_sec)}",
        f"speakers: {metadata.speaker_count}",
        f"language: {metadata.language}",
        f"model: {metadata.model}",
        f"provider: {metadata.provider}",
        f"created: {created}",
        "---",
        "",
    ]
    body = ["## 전사", ""]
    for u in utterances:
        body.append(f"**[S{u.speaker} {_hms(u.start)}]** {u.text}")
        body.append("")
    return "\n".join(front + body)


def to_txt(utterances: list[Utterance]) -> str:
    """플레인 텍스트. 화자/타임스탬프 없음, 줄바꿈으로만 구분."""
    return "\n".join(u.text for u in utterances) + "\n"


def _srt_ts(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _hms(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
