from __future__ import annotations

import asyncio
import logging
import mimetypes
from pathlib import Path

import httpx

from cheroki.core.result import TranscriptionResult
from cheroki.core.transcribers.base import TranscriptionError
from cheroki.core.types import TranscriptionMetadata, Utterance

logger = logging.getLogger(__name__)

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"


class DeepgramTranscriber:
    """Deepgram 사전 녹취 API 래퍼. Nova-2 + 한국어 + 화자분리 기본."""

    def __init__(
        self,
        api_key: str,
        model: str = "nova-2",
        language: str = "ko",
        timeout: float = 1800.0,
    ) -> None:
        if not api_key:
            raise ValueError("Deepgram API 키가 비어 있습니다 (DEEPGRAM_API_KEY).")
        self.api_key = api_key
        self.model = model
        self.language = language
        self.timeout = timeout

    async def transcribe(self, audio_path: Path) -> TranscriptionResult:
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"오디오 파일 없음: {audio_path}")

        logger.info("Deepgram 요청 시작: %s (%.1f MB)", audio_path.name, audio_path.stat().st_size / 1e6)

        audio_bytes = await asyncio.to_thread(audio_path.read_bytes)
        content_type = mimetypes.guess_type(audio_path.name)[0] or "audio/*"

        params = {
            "model": self.model,
            "language": self.language,
            "diarize": "true",
            "punctuate": "true",
            "utterances": "true",
            "smart_format": "true",
        }
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": content_type,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    DEEPGRAM_URL,
                    params=params,
                    headers=headers,
                    content=audio_bytes,
                )
            except httpx.HTTPError as exc:
                raise TranscriptionError(f"Deepgram 요청 실패: {exc}") from exc

        if response.status_code != 200:
            raise TranscriptionError(
                f"Deepgram HTTP {response.status_code}: {response.text[:500]}",
                payload={"status": response.status_code, "body": response.text},
            )

        payload = response.json()
        logger.info("Deepgram 응답 수신: %d bytes", len(response.content))

        return self._parse(payload)

    def _parse(self, payload: dict) -> TranscriptionResult:
        results = payload.get("results") or {}
        utterances_raw = results.get("utterances") or []

        utterances: list[Utterance] = []
        for u in utterances_raw:
            text = (u.get("transcript") or "").strip()
            if not text:
                continue
            utterances.append(
                Utterance(
                    speaker=int(u.get("speaker") or 0),
                    start=float(u.get("start") or 0.0),
                    end=float(u.get("end") or 0.0),
                    text=text,
                    confidence=float(u.get("confidence") or 0.0),
                )
            )

        meta_raw = payload.get("metadata") or {}
        duration = float(meta_raw.get("duration") or 0.0)
        speaker_count = len({u.speaker for u in utterances})

        metadata = TranscriptionMetadata(
            duration_sec=duration,
            speaker_count=speaker_count,
            language=self.language,
            model=self.model,
            provider="deepgram",
            extra={
                "request_id": meta_raw.get("request_id"),
                "sha256": meta_raw.get("sha256"),
            },
        )

        return TranscriptionResult(
            utterances=utterances,
            metadata=metadata,
            raw_response=payload,
        )
