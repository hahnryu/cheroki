from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class Utterance:
    speaker: int
    start: float
    end: float
    text: str
    confidence: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Utterance:
        return cls(
            speaker=int(data["speaker"]),
            start=float(data["start"]),
            end=float(data["end"]),
            text=str(data["text"]),
            confidence=float(data["confidence"]),
        )


@dataclass(slots=True)
class TranscriptionMetadata:
    duration_sec: float
    speaker_count: int
    language: str = "ko"
    model: str = "nova-2"
    provider: str = "deepgram"
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TranscriptionMetadata:
        return cls(
            duration_sec=float(data["duration_sec"]),
            speaker_count=int(data["speaker_count"]),
            language=str(data.get("language", "ko")),
            model=str(data.get("model", "nova-2")),
            provider=str(data.get("provider", "deepgram")),
            extra=dict(data.get("extra", {})),
        )
