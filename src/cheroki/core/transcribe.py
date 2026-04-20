from __future__ import annotations

import logging
from pathlib import Path

from cheroki.core.result import TranscriptionResult
from cheroki.core.transcribers.base import Transcriber
from cheroki.core.transcribers.deepgram import DeepgramTranscriber

logger = logging.getLogger(__name__)


async def transcribe_audio(
    audio_path: str | Path,
    *,
    transcriber: Transcriber | None = None,
) -> TranscriptionResult:
    """오디오 파일 하나를 전사한다.

    Parameters
    ----------
    audio_path:
        파일 경로. 상대/절대 모두 가능.
    transcriber:
        구현체를 주입. 없으면 환경변수에서 Deepgram 설정을 읽어 기본 구현체 사용.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"오디오 파일 없음: {path}")

    if transcriber is None:
        transcriber = _default_transcriber()

    logger.info("전사 시작: %s", path.name)
    result = await transcriber.transcribe(path)
    logger.info(
        "전사 완료: %s (화자 %d명, %.1f초, %d utterance)",
        path.name,
        result.speaker_count,
        result.duration_sec,
        len(result.utterances),
    )
    return result


def _default_transcriber() -> Transcriber:
    from cheroki.config import load_config

    cfg = load_config()
    return DeepgramTranscriber(
        api_key=cfg.deepgram_api_key,
        model=cfg.deepgram_model,
    )
