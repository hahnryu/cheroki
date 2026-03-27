"""transcriber 모듈 테스트.

실제 Whisper 모델 없이도 구조를 검증하는 유닛 테스트.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch
import math

import pytest

from cheroki.transcriber import Segment, TranscriptionResult, Transcriber


# --- Segment / TranscriptionResult 구조 테스트 ---

def test_segment_to_dict():
    seg = Segment(start=1.0, end=2.5, text="안녕하세요", confidence=0.95)
    d = seg.to_dict()
    assert d["start"] == 1.0
    assert d["end"] == 2.5
    assert d["text"] == "안녕하세요"
    assert d["confidence"] == 0.95


def test_transcription_result_full_text():
    result = TranscriptionResult(
        source_file="test.wav",
        language="ko",
        language_probability=0.99,
        duration=10.0,
        segments=[
            Segment(start=0.0, end=3.0, text="첫 번째", confidence=0.9),
            Segment(start=3.0, end=6.0, text="두 번째", confidence=0.85),
            Segment(start=6.0, end=10.0, text="세 번째", confidence=0.92),
        ],
    )
    assert result.full_text == "첫 번째 두 번째 세 번째"


def test_transcription_result_to_dict():
    result = TranscriptionResult(
        source_file="test.wav",
        language="ko",
        language_probability=0.99,
        duration=5.0,
        segments=[
            Segment(start=0.0, end=5.0, text="테스트", confidence=0.9),
        ],
    )
    d = result.to_dict()
    assert d["source_file"] == "test.wav"
    assert d["language"] == "ko"
    assert d["full_text"] == "테스트"
    assert len(d["segments"]) == 1


def test_from_config():
    config = {
        "whisper": {
            "model": "small",
            "device": "cpu",
            "compute_type": "int8",
            "language": "ko",
        }
    }
    t = Transcriber.from_config(config)
    assert t.model_size == "small"
    assert t.device == "cpu"
    assert t.compute_type == "int8"
    assert t.language == "ko"


def test_transcribe_missing_file():
    t = Transcriber(model_size="tiny")
    with pytest.raises(FileNotFoundError):
        t.transcribe(Path("/nonexistent/file.wav"))


# --- Mock 기반 전사 통합 테스트 ---

@dataclass
class _FakeSegment:
    start: float
    end: float
    text: str
    avg_logprob: float


@dataclass
class _FakeInfo:
    language: str
    language_probability: float
    duration: float


def test_transcribe_with_mock():
    """WhisperModel을 mock하여 전체 전사 흐름을 검증."""
    fake_segments = [
        _FakeSegment(start=0.0, end=3.0, text="안녕하세요", avg_logprob=-0.2),
        _FakeSegment(start=3.0, end=6.0, text="테스트입니다", avg_logprob=-0.5),
    ]
    fake_info = _FakeInfo(language="ko", language_probability=0.98, duration=6.0)

    mock_model = MagicMock()
    mock_model.transcribe.return_value = (iter(fake_segments), fake_info)

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = Path(tmp) / "test.wav"
        audio_path.write_bytes(b"RIFF" + b"\x00" * 100)

        t = Transcriber(model_size="tiny")
        t._model = mock_model

        result = t.transcribe(audio_path)

    assert result.language == "ko"
    assert len(result.segments) == 2
    assert result.segments[0].text == "안녕하세요"
    assert result.segments[1].text == "테스트입니다"
    assert 0.0 < result.segments[0].confidence <= 1.0
    assert result.duration == 6.0
