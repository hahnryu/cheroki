from __future__ import annotations

import asyncio
import logging
import math
import mimetypes
from pathlib import Path

import httpx

from cheroki.core.result import TranscriptionResult
from cheroki.core.transcribers.base import TranscriptionError
from cheroki.core.types import TranscriptionMetadata, Utterance

logger = logging.getLogger(__name__)

SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"


class ScribeTranscriber:
    """ElevenLabs Scribe Speech-to-Text API 래퍼. scribe_v2 + 한국어 + diarize 기본.

    Scribe는 word 단위 타임스탬프만 주므로 speaker_id가 바뀌는 지점을 경계로
    Utterance로 묶는다. confidence는 word들의 logprob 평균을 exp한 값.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "scribe_v2",
        language: str = "ko",
        keyterms: list[str] | None = None,
        num_speakers: int | None = None,
        timeout: float = 1800.0,
    ) -> None:
        if not api_key:
            raise ValueError("ElevenLabs API 키가 비어 있습니다 (ELEVENLABS_API_KEY).")
        self.api_key = api_key
        self.model = model
        self.language = language
        self.keyterms = keyterms or []
        self.num_speakers = num_speakers
        self.timeout = timeout

    async def transcribe(self, audio_path: Path) -> TranscriptionResult:
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"오디오 파일 없음: {audio_path}")

        size_mb = audio_path.stat().st_size / 1e6
        logger.info("Scribe 요청 시작: %s (%.1f MB)", audio_path.name, size_mb)

        audio_bytes = await asyncio.to_thread(audio_path.read_bytes)
        content_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"

        # httpx multipart: list[tuple] 로 주면 AsyncClient 경로가 sync stream으로 빠지는
        # 이슈가 있어 dict로 전달한다. 같은 키 반복은 dict value에 list를 담으면 된다.
        form: dict[str, str | list[str]] = {
            "model_id": self.model,
            "language_code": self.language,
            "diarize": "true",
            "timestamps_granularity": "word",
        }
        if self.num_speakers is not None:
            form["num_speakers"] = str(self.num_speakers)
        if self.keyterms:
            form["keyterms"] = list(self.keyterms)

        files = {"file": (audio_path.name, audio_bytes, content_type)}
        headers = {"xi-api-key": self.api_key}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    SCRIBE_URL,
                    headers=headers,
                    data=form,
                    files=files,
                )
            except httpx.HTTPError as exc:
                raise TranscriptionError(f"Scribe 요청 실패: {exc}") from exc

        if response.status_code != 200:
            raise TranscriptionError(
                f"Scribe HTTP {response.status_code}: {response.text[:500]}",
                payload={"status": response.status_code, "body": response.text},
            )

        payload = response.json()
        logger.info("Scribe 응답 수신: %d bytes", len(response.content))

        return self._parse(payload)

    def _parse(self, payload: dict) -> TranscriptionResult:
        words = payload.get("words") or []
        utterances = _group_words_by_speaker(words)

        duration = float(payload.get("audio_duration_secs") or 0.0)
        if duration == 0.0 and utterances:
            duration = utterances[-1].end

        speaker_count = len({u.speaker for u in utterances})
        language = str(payload.get("language_code") or self.language)

        metadata = TranscriptionMetadata(
            duration_sec=duration,
            speaker_count=speaker_count,
            language=language,
            model=self.model,
            provider="elevenlabs",
            extra={
                "language_probability": payload.get("language_probability"),
            },
        )

        return TranscriptionResult(
            utterances=utterances,
            metadata=metadata,
            raw_response=payload,
        )


def _group_words_by_speaker(words: list[dict]) -> list[Utterance]:
    """word 배열을 speaker 경계로 Utterance 리스트로 묶는다.

    type='audio_event'는 제외. type='spacing'은 앞뒤 word에 붙여 문장 공백 복원에 사용.
    speaker_id 문자열을 처음 등장 순서대로 0,1,2...에 매핑한다.
    """
    speaker_map: dict[str, int] = {}

    def speaker_index(raw: object) -> int:
        key = str(raw) if raw is not None else ""
        if key not in speaker_map:
            speaker_map[key] = len(speaker_map)
        return speaker_map[key]

    utterances: list[Utterance] = []
    cur_speaker: int | None = None
    cur_texts: list[str] = []
    cur_start: float | None = None
    cur_end: float = 0.0
    cur_logprobs: list[float] = []

    def flush() -> None:
        if cur_speaker is None or cur_start is None:
            return
        text = "".join(cur_texts).strip()
        if not text:
            return
        if cur_logprobs:
            mean_lp = sum(cur_logprobs) / len(cur_logprobs)
            confidence = max(0.0, min(1.0, math.exp(mean_lp)))
        else:
            confidence = 0.0
        utterances.append(
            Utterance(
                speaker=cur_speaker,
                start=cur_start,
                end=cur_end,
                text=text,
                confidence=confidence,
            )
        )

    for w in words:
        wtype = w.get("type") or "word"
        if wtype == "audio_event":
            continue

        start = float(w.get("start") or 0.0)
        end = float(w.get("end") or start)
        text = str(w.get("text") or "")
        speaker = speaker_index(w.get("speaker_id"))

        if cur_speaker is None:
            cur_speaker = speaker
            cur_start = start

        if speaker != cur_speaker:
            flush()
            cur_speaker = speaker
            cur_texts = []
            cur_start = start
            cur_end = end
            cur_logprobs = []

        cur_texts.append(text)
        cur_end = max(cur_end, end)
        if wtype == "word":
            lp = w.get("logprob")
            if lp is not None:
                cur_logprobs.append(float(lp))

    flush()
    return utterances
