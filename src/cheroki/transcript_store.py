"""전사 결과 저장/로드 모듈."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cheroki.transcriber import TranscriptionResult, Segment


def save_transcript(result: TranscriptionResult, transcripts_dir: Path, file_id: str) -> Path:
    """전사 결과를 JSON으로 저장한다.

    Returns:
        저장된 JSON 파일 경로.
    """
    transcripts_dir = Path(transcripts_dir)
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    data = result.to_dict()
    data["file_id"] = file_id

    out_path = transcripts_dir / f"{file_id}.transcript.json"
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def load_transcript(path: Path) -> TranscriptionResult:
    """저장된 JSON에서 TranscriptionResult를 복원한다."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    segments = [
        Segment(
            start=seg["start"],
            end=seg["end"],
            text=seg["text"],
            confidence=seg["confidence"],
        )
        for seg in data.get("segments", [])
    ]

    return TranscriptionResult(
        source_file=data["source_file"],
        language=data["language"],
        language_probability=data["language_probability"],
        duration=data["duration"],
        segments=segments,
    )
