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
    """단순 Markdown. 라이브러리 사용자가 빠르게 호출할 때."""
    frontmatter = {"title": title or "녹취"}
    return to_markdown_with_frontmatter(utterances, metadata, frontmatter=frontmatter)


def to_markdown_with_frontmatter(
    utterances: list[Utterance],
    metadata: TranscriptionMetadata,
    *,
    frontmatter: dict,
) -> str:
    """확장 frontmatter를 받는 Markdown 렌더러.

    내부 기본값(duration, speakers, language, model, provider, created)이 먼저 깔리고,
    frontmatter 인자가 그 위를 덮어쓴다. 값이 None이면 해당 키는 출력에서 생략.
    """
    created = datetime.now(UTC).isoformat(timespec="seconds")
    fields: dict = {
        "title": "녹취",
        "duration": _hms(metadata.duration_sec),
        "speakers": metadata.speaker_count,
        "language": metadata.language,
        "model": metadata.model,
        "provider": metadata.provider,
        "created": created,
    }
    fields.update({k: v for k, v in frontmatter.items() if v is not None})

    lines = ["---"]
    for key, value in fields.items():
        if value is None:
            continue
        lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    lines.append("")
    lines.append("## 전사")
    lines.append("")

    for u in utterances:
        lines.append(f"**[S{u.speaker} {_hms(u.start)}]** {u.text}")
        lines.append("")

    return "\n".join(lines)


def to_txt(utterances: list[Utterance]) -> str:
    """플레인 텍스트. 화자/타임스탬프 없음, 줄바꿈으로만 구분."""
    return "\n".join(u.text for u in utterances) + "\n"


def _yaml_scalar(value) -> str:
    """YAML 스칼라 인코딩. 꼭 필요할 때만 따옴표."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    needs_quote = (
        "\n" in s
        or s != s.strip()
        or (s and s[0] in "!&*>|%@`\"'#[{")
        or s.lower() in {"null", "true", "false", "yes", "no", "on", "off", "~"}
    )
    if needs_quote:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


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
