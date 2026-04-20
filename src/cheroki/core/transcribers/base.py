from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from cheroki.core.result import TranscriptionResult


class TranscriptionError(RuntimeError):
    """전사 실패. 원인을 message에, 상세를 payload에."""

    def __init__(self, message: str, *, payload: dict | None = None) -> None:
        super().__init__(message)
        self.payload = payload or {}


@runtime_checkable
class Transcriber(Protocol):
    """전사 엔진 인터페이스.

    구현체는 오디오 파일 하나를 받아 TranscriptionResult를 돌려준다.
    """

    async def transcribe(self, audio_path: Path) -> TranscriptionResult: ...
