from __future__ import annotations

from dataclasses import dataclass, field

from cheroki.core.exporter import to_markdown, to_srt, to_txt
from cheroki.core.types import TranscriptionMetadata, Utterance


@dataclass(slots=True)
class TranscriptionResult:
    utterances: list[Utterance]
    metadata: TranscriptionMetadata
    raw_response: dict = field(default_factory=dict)

    @property
    def duration_sec(self) -> float:
        return self.metadata.duration_sec

    @property
    def speaker_count(self) -> int:
        return self.metadata.speaker_count

    @property
    def text(self) -> str:
        """화자 + 타임스탬프가 포함된 서술형 텍스트. 미리보기/공유에 적합."""
        return "\n\n".join(
            f"[S{u.speaker} {_fmt_ts(u.start)}] {u.text}" for u in self.utterances
        )

    @property
    def plain_text(self) -> str:
        """메타정보 없는 순수 본문. 검색/임베딩에 적합."""
        return " ".join(u.text for u in self.utterances)

    def to_srt(self) -> str:
        return to_srt(self.utterances)

    def to_markdown(self, title: str | None = None) -> str:
        return to_markdown(self.utterances, self.metadata, title=title)

    def to_txt(self) -> str:
        return to_txt(self.utterances)

    def to_dict(self) -> dict:
        return {
            "utterances": [u.to_dict() for u in self.utterances],
            "metadata": self.metadata.to_dict(),
            "raw_response": self.raw_response,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TranscriptionResult:
        return cls(
            utterances=[Utterance.from_dict(u) for u in data.get("utterances", [])],
            metadata=TranscriptionMetadata.from_dict(data["metadata"]),
            raw_response=dict(data.get("raw_response", {})),
        )


def _fmt_ts(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
