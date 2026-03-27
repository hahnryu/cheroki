"""Whisper 전사 엔진 모듈 — 로컬(faster-whisper) / API(OpenAI) 전환 지원."""

from __future__ import annotations

import math
import structlog
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

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


# ── 로컬 전사 (faster-whisper) ────────────────────────

class LocalTranscriber:
    """faster-whisper 기반 로컬 전사 엔진."""

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
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel
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
        """음성 파일을 로컬에서 전사한다."""
        audio_path = Path(audio_path)
        if not audio_path.is_file():
            raise FileNotFoundError(f"음성 파일을 찾을 수 없습니다: {audio_path}")

        model = self._get_model()
        logger.info("transcription_start", mode="local", file=str(audio_path))

        segments_gen, info = model.transcribe(
            str(audio_path),
            language=self.language,
            beam_size=5,
            word_timestamps=False,
            vad_filter=True,
        )

        segments: list[Segment] = []
        for seg in segments_gen:
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

        logger.info("transcription_complete", mode="local", segments=len(segments), duration=result.duration)
        return result


# ── API 전사 (OpenAI Whisper API) ─────────────────────

class APITranscriber:
    """OpenAI Whisper API 기반 전사 엔진."""

    def __init__(
        self,
        api_key: str,
        model: str = "whisper-1",
        language: str = "ko",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.language = language
        if not self.api_key:
            raise ValueError("openai.api_key가 config.yaml에 설정되지 않았습니다")

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """음성 파일을 OpenAI API로 전사한다."""
        import json
        import urllib.request
        import urllib.error
        from email.mime.multipart import MIMEMultipart

        audio_path = Path(audio_path)
        if not audio_path.is_file():
            raise FileNotFoundError(f"음성 파일을 찾을 수 없습니다: {audio_path}")

        logger.info("transcription_start", mode="api", file=str(audio_path))

        # multipart/form-data 직접 구성
        boundary = "----CherokiBoundary"
        body = _build_multipart(
            audio_path,
            model=self.model,
            language=self.language,
            response_format="verbose_json",
            timestamp_granularities="segment",
            boundary=boundary,
        )

        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # API 응답 → TranscriptionResult 변환
        segments: list[Segment] = []
        for seg in data.get("segments", []):
            segments.append(Segment(
                start=round(seg["start"], 3),
                end=round(seg["end"], 3),
                text=seg["text"],
                confidence=round(math.exp(seg.get("avg_logprob", -1.0)), 4),
            ))

        duration = data.get("duration", 0.0)
        if not segments and data.get("text"):
            # segments가 없으면 전체 텍스트를 하나의 세그먼트로
            segments.append(Segment(start=0.0, end=duration, text=data["text"], confidence=0.9))

        result = TranscriptionResult(
            source_file=str(audio_path),
            language=data.get("language", self.language),
            language_probability=1.0,
            duration=round(duration, 3),
            segments=segments,
        )

        logger.info("transcription_complete", mode="api", segments=len(segments), duration=result.duration)
        return result


def _build_multipart(
    audio_path: Path,
    boundary: str,
    **fields: str,
) -> bytes:
    """multipart/form-data 바디를 직접 구성한다."""
    parts: list[bytes] = []

    for key, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())

    # 파일 파트
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{audio_path.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n".encode()
    )
    parts.append(audio_path.read_bytes())
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())

    return b"".join(parts)


# ── 팩토리: config에서 적절한 Transcriber 생성 ────────

# 하위 호환성 별칭
Transcriber = LocalTranscriber


def create_transcriber(config: dict[str, Any]) -> LocalTranscriber | APITranscriber:
    """config.yaml의 whisper.mode에 따라 적절한 전사 엔진을 생성한다.

    mode: "local" (기본) → LocalTranscriber (faster-whisper)
    mode: "api"         → APITranscriber (OpenAI Whisper API)
    """
    whisper_cfg = config.get("whisper", {})
    mode = whisper_cfg.get("mode", "local")

    if mode == "api":
        openai_cfg = config.get("openai", {})
        api_key = openai_cfg.get("api_key", "")
        return APITranscriber(
            api_key=api_key,
            model=whisper_cfg.get("api_model", "whisper-1"),
            language=whisper_cfg.get("language", "ko"),
        )

    return LocalTranscriber(
        model_size=whisper_cfg.get("model", "medium"),
        device=whisper_cfg.get("device", "cpu"),
        compute_type=whisper_cfg.get("compute_type", "int8"),
        language=whisper_cfg.get("language", "ko"),
    )
