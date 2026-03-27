"""Whisper 전사 엔진 모듈."""

from __future__ import annotations

import structlog
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel

logger = structlog.get_logger()


@dataclass
class Segment:
    """전사된 하나의 세그먼트."""
    start: float
    end: float
    text: str
    confidence: float  # avg_logprob → probability 근사

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TranscriptionResult:
    """전사 결과 전체."""
    source_file: str
    language: str
    language_probability: float
    duration: float
    segments: list[Segment] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return " ".join(seg.text.strip() for seg in self.segments)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "language": self.language,
            "language_probability": self.language_probability,
            "duration": self.duration,
            "full_text": self.full_text,
            "segments": [seg.to_dict() for seg in self.segments],
        }


class Transcriber:
    """faster-whisper 기반 전사 엔진."""

    def __init__(
        self,
        model_size: str = "medium",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "ko",
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self._model: WhisperModel | None = None

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            logger.info(
                "whisper_model_loading",
                model=self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """음성 파일을 전사한다."""
        audio_path = Path(audio_path)
        if not audio_path.is_file():
            raise FileNotFoundError(f"음성 파일을 찾을 수 없습니다: {audio_path}")

        model = self._get_model()
        logger.info("transcription_start", file=str(audio_path))

        segments_gen, info = model.transcribe(
            str(audio_path),
            language=self.language,
            beam_size=5,
            word_timestamps=False,
            vad_filter=True,
        )

        segments: list[Segment] = []
        for seg in segments_gen:
            # avg_logprob를 확률로 근사 변환
            import math
            confidence = math.exp(seg.avg_logprob) if seg.avg_logprob else 0.0
            confidence = min(max(confidence, 0.0), 1.0)

            segments.append(Segment(
                start=round(seg.start, 3),
                end=round(seg.end, 3),
                text=seg.text,
                confidence=round(confidence, 4),
            ))

        result = TranscriptionResult(
            source_file=str(audio_path),
            language=info.language,
            language_probability=round(info.language_probability, 4),
            duration=round(info.duration, 3),
            segments=segments,
        )

        logger.info(
            "transcription_complete",
            file=str(audio_path),
            segments=len(segments),
            duration=result.duration,
        )
        return result

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Transcriber:
        """config dict에서 Transcriber를 생성."""
        whisper_cfg = config.get("whisper", {})
        return cls(
            model_size=whisper_cfg.get("model", "medium"),
            device=whisper_cfg.get("device", "cpu"),
            compute_type=whisper_cfg.get("compute_type", "int8"),
            language=whisper_cfg.get("language", "ko"),
        )
