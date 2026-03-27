"""전사 파이프라인 — 원본 저장 → 전사 → 결과 저장을 한 번에."""

from __future__ import annotations

import structlog
from pathlib import Path
from typing import Any

from cheroki.config import get_config
from cheroki.storage import store_original
from cheroki.transcriber import create_transcriber, TranscriptionResult
from cheroki.transcript_store import save_transcript

logger = structlog.get_logger()


def run_pipeline(
    audio_path: Path,
    config: dict[str, Any] | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """음성 파일 하나를 전사 파이프라인으로 처리한다.

    Returns:
        {file_id, metadata_path, transcript_path, result}
    """
    config = config or get_config(config_path)
    audio_path = Path(audio_path)

    # 1. 원본 저장
    logger.info("pipeline_store", file=str(audio_path))
    metadata = store_original(audio_path, Path(config["paths"]["originals"]))
    file_id = metadata["file_id"]

    # 2. 전사
    logger.info("pipeline_transcribe", file_id=file_id)
    transcriber = create_transcriber(config)
    result = transcriber.transcribe(audio_path)

    # 3. 결과 저장
    transcript_path = save_transcript(
        result,
        Path(config["paths"]["transcripts"]),
        file_id,
    )
    logger.info("pipeline_complete", file_id=file_id, transcript=str(transcript_path))

    return {
        "file_id": file_id,
        "metadata": metadata,
        "transcript_path": str(transcript_path),
        "result": result,
    }
