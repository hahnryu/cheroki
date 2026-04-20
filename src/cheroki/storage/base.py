from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from cheroki.core.result import TranscriptionResult


@runtime_checkable
class Store(Protocol):
    def save(self, result: TranscriptionResult, metadata: dict) -> str:
        """전사 결과를 저장하고 record_id를 반환."""

    def get(self, record_id: str) -> dict | None:
        """record_id로 조회. 없으면 None."""

    def list_recent(self, limit: int = 5) -> list[dict]:
        """최근 created_at 역순으로 N건 반환."""
