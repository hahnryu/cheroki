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

_MAX_API_FILE_SIZE = 24 * 1024 * 1024  # 24MB (25MB 제한에 여유)
_CHUNK_MINUTES = 10  # 분할 시 청크 크기 (분)


class APITranscriber:
    """OpenAI Whisper API 기반 전사 엔진.

    25MB 초과 파일은 ffmpeg로 분할하여 청크별 전사 후 병합한다.
    """

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
        audio_path = Path(audio_path)
        if not audio_path.is_file():
            raise FileNotFoundError(f"음성 파일을 찾을 수 없습니다: {audio_path}")

        file_size = audio_path.stat().st_size
        logger.info("transcription_start", mode="api", file=str(audio_path), size_mb=round(file_size / 1024 / 1024, 1))

        if file_size > _MAX_API_FILE_SIZE:
            return self._transcribe_chunked(audio_path)

        return self._transcribe_single(audio_path)

    def _transcribe_single(self, audio_path: Path) -> TranscriptionResult:
        """단일 파일 전사."""
        import json
        import urllib.request
        import urllib.error

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

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error("api_error", status=e.code, body=error_body)
            raise RuntimeError(f"OpenAI API 오류 ({e.code}): {error_body}") from e

        return self._parse_response(data, str(audio_path))

    def _transcribe_chunked(self, audio_path: Path) -> TranscriptionResult:
        """큰 파일을 분할하여 전사한다 (ffmpeg 필요)."""
        import shutil
        import subprocess
        import tempfile

        if not shutil.which("ffmpeg"):
            raise RuntimeError(
                f"파일이 {audio_path.stat().st_size // 1024 // 1024}MB로 OpenAI API 제한(25MB)을 초과합니다. "
                f"분할 전사를 위해 ffmpeg를 설치하세요: sudo apt install ffmpeg"
            )

        logger.info("transcription_chunking", file=str(audio_path))

        # 음성 길이 확인
        duration = _get_duration(audio_path)
        chunk_seconds = _CHUNK_MINUTES * 60

        all_segments: list[Segment] = []
        total_duration = 0.0
        detected_language = self.language

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            chunk_idx = 0
            offset = 0.0

            while offset < duration:
                chunk_file = tmp_path / f"chunk_{chunk_idx:03d}.mp3"

                # ffmpeg로 청크 추출 (mp3로 압축하여 용량 감소)
                cmd = [
                    "ffmpeg", "-y", "-i", str(audio_path),
                    "-ss", str(offset),
                    "-t", str(chunk_seconds),
                    "-ac", "1",           # 모노
                    "-ar", "16000",       # 16kHz
                    "-b:a", "64k",        # 64kbps
                    str(chunk_file),
                ]
                subprocess.run(cmd, capture_output=True, check=True)

                logger.info("transcription_chunk", chunk=chunk_idx, offset=offset)
                result = self._transcribe_single(chunk_file)

                # 타임스탬프 오프셋 적용
                for seg in result.segments:
                    all_segments.append(Segment(
                        start=round(seg.start + offset, 3),
                        end=round(seg.end + offset, 3),
                        text=seg.text,
                        confidence=seg.confidence,
                    ))

                total_duration = max(total_duration, result.duration + offset)
                detected_language = result.language
                offset += chunk_seconds
                chunk_idx += 1

        return TranscriptionResult(
            source_file=str(audio_path),
            language=detected_language,
            language_probability=1.0,
            duration=round(total_duration, 3),
            segments=all_segments,
        )

    def _parse_response(self, data: dict[str, Any], source_file: str) -> TranscriptionResult:
        """API 응답을 TranscriptionResult로 변환."""
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
            segments.append(Segment(start=0.0, end=duration, text=data["text"], confidence=0.9))

        result = TranscriptionResult(
            source_file=source_file,
            language=data.get("language", self.language),
            language_probability=1.0,
            duration=round(duration, 3),
            segments=segments,
        )

        logger.info("transcription_complete", mode="api", segments=len(segments), duration=result.duration)
        return result


def _get_duration(audio_path: Path) -> float:
    """ffprobe로 음성 파일의 길이(초)를 구한다."""
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 3600.0  # fallback: 1시간으로 가정


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
