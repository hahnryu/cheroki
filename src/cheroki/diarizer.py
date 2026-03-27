"""화자 분리 모듈."""

from __future__ import annotations

import structlog
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cheroki.transcriber import TranscriptionResult, Segment

logger = structlog.get_logger()


@dataclass
class SpeakerSegment:
    """화자 구간."""
    speaker: str
    start: float
    end: float


def assign_speakers(
    result: TranscriptionResult,
    speaker_segments: list[SpeakerSegment],
) -> TranscriptionResult:
    """전사 세그먼트에 화자 라벨을 부착한다.

    각 전사 세그먼트의 중간점이 어떤 화자 구간에 속하는지로 매칭.
    """
    new_segments: list[Segment] = []

    for seg in result.segments:
        midpoint = (seg.start + seg.end) / 2
        speaker = _find_speaker(midpoint, speaker_segments)

        # Segment에 speaker를 동적으로 부착
        new_seg = Segment(
            start=seg.start,
            end=seg.end,
            text=seg.text,
            confidence=seg.confidence,
        )
        # 동적 속성으로 speaker 추가 (exporter에서 getattr로 접근)
        object.__setattr__(new_seg, "speaker", speaker)
        new_segments.append(new_seg)

    return TranscriptionResult(
        source_file=result.source_file,
        language=result.language,
        language_probability=result.language_probability,
        duration=result.duration,
        segments=new_segments,
    )


def _find_speaker(time_point: float, segments: list[SpeakerSegment]) -> str:
    """시점에 해당하는 화자를 찾는다."""
    for seg in segments:
        if seg.start <= time_point <= seg.end:
            return seg.speaker
    return "UNKNOWN"


def diarize(audio_path: Path) -> list[SpeakerSegment]:
    """pyannote-audio로 화자 분리를 수행한다.

    pyannote-audio가 설치되어 있지 않으면 빈 리스트를 반환.
    """
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        logger.warning("pyannote_not_installed", msg="pyannote-audio 미설치. 화자 분리 건너뜀.")
        return []

    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
        )
        diarization = pipeline(str(audio_path))

        segments: list[SpeakerSegment] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(SpeakerSegment(
                speaker=speaker,
                start=turn.start,
                end=turn.end,
            ))

        logger.info("diarization_complete", speakers=len(set(s.speaker for s in segments)))
        return segments

    except Exception:
        logger.exception("diarization_error")
        return []
