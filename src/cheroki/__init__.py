"""Cheroki · 한국어 음성 전사 모듈.

공개 API:
    from cheroki import transcribe_audio, TranscriptionResult, Utterance
"""
from cheroki.core.result import TranscriptionResult
from cheroki.core.transcribe import transcribe_audio
from cheroki.core.types import TranscriptionMetadata, Utterance

__all__ = [
    "TranscriptionMetadata",
    "TranscriptionResult",
    "Utterance",
    "transcribe_audio",
]

__version__ = "0.1.0"
