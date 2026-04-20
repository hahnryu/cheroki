from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from cheroki.core.result import TranscriptionResult
from cheroki.storage.ids import generate_short_id

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS transcripts (
    id TEXT PRIMARY KEY,
    tg_user_id INTEGER,
    tg_username TEXT,
    tg_chat_id INTEGER,
    tg_message_id INTEGER,
    file_name TEXT,
    file_size_bytes INTEGER,
    file_format TEXT,
    caption TEXT,
    session_title TEXT,
    romanized_slug TEXT,
    recording_date TEXT,
    place TEXT,
    source TEXT,
    status TEXT NOT NULL,
    error TEXT,
    duration_sec REAL,
    speaker_count INTEGER,
    language TEXT,
    model TEXT,
    audio_path TEXT,
    srt_path TEXT,
    md_path TEXT,
    txt_path TEXT,
    raw_json_path TEXT,
    transcript_text TEXT,
    created_at TEXT NOT NULL,
    received_at TEXT,
    completed_at TEXT
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_tg_user ON transcripts(tg_user_id);
CREATE INDEX IF NOT EXISTS idx_status ON transcripts(status);
CREATE INDEX IF NOT EXISTS idx_created ON transcripts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recording_date ON transcripts(recording_date);
"""

# 기존 DB에 있을 수 있는데 이번 스키마에 추가된 컬럼들. 안전하게 ALTER.
_ADDITIVE_COLUMNS = {
    "file_format": "TEXT",
    "romanized_slug": "TEXT",
    "recording_date": "TEXT",
    "place": "TEXT",
    "source": "TEXT",
    "received_at": "TEXT",
}


class SQLiteStore:
    """SQLite 기반 transcripts 저장소."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(CREATE_TABLE_SQL)
        self._migrate_schema()
        self._conn.executescript(CREATE_INDEX_SQL)
        self._conn.commit()

    def _migrate_schema(self) -> None:
        """기존 DB 파일에 새 컬럼을 추가 (idempotent)."""
        existing = {r["name"] for r in self._conn.execute("PRAGMA table_info(transcripts)")}
        for col, col_type in _ADDITIVE_COLUMNS.items():
            if col not in existing:
                self._conn.execute(f"ALTER TABLE transcripts ADD COLUMN {col} {col_type}")
                logger.info("스키마 확장: transcripts.%s", col)

    def close(self) -> None:
        self._conn.close()

    # ---------- 생성 ----------

    def create_pending(
        self,
        *,
        tg_user_id: int | None = None,
        tg_username: str | None = None,
        tg_chat_id: int | None = None,
        tg_message_id: int | None = None,
        file_name: str | None = None,
        file_size_bytes: int | None = None,
        file_format: str | None = None,
        caption: str | None = None,
        session_title: str | None = None,
        romanized_slug: str | None = None,
        recording_date: date | str | None = None,
        place: str | None = None,
        source: str = "telegram",
        received_at: datetime | str | None = None,
    ) -> str:
        """pending 상태로 레코드 생성. short ID 반환. 충돌 시 재시도."""
        for _ in range(10):
            rec_id = generate_short_id()
            try:
                self._conn.execute(
                    """
                    INSERT INTO transcripts (
                        id, tg_user_id, tg_username, tg_chat_id, tg_message_id,
                        file_name, file_size_bytes, file_format,
                        caption, session_title, romanized_slug,
                        recording_date, place, source,
                        status, created_at, received_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        rec_id, tg_user_id, tg_username, tg_chat_id, tg_message_id,
                        file_name, file_size_bytes, file_format,
                        caption, session_title, romanized_slug,
                        _date_str(recording_date), place, source,
                        _now(), _dt_str(received_at),
                    ),
                )
                self._conn.commit()
                logger.info("레코드 생성: %s (file=%s, slug=%s)", rec_id, file_name, romanized_slug)
                return rec_id
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("short ID 생성 재시도 한계 초과")

    # ---------- 업데이트 ----------

    def set_audio_path(self, record_id: str, audio_path: str | Path) -> None:
        self._conn.execute(
            "UPDATE transcripts SET audio_path = ? WHERE id = ?",
            (str(audio_path), record_id),
        )
        self._conn.commit()

    def set_slug(self, record_id: str, slug: str) -> None:
        self._conn.execute(
            "UPDATE transcripts SET romanized_slug = ? WHERE id = ?",
            (slug, record_id),
        )
        self._conn.commit()

    def set_processing(self, record_id: str) -> None:
        self._conn.execute(
            "UPDATE transcripts SET status = 'processing' WHERE id = ?",
            (record_id,),
        )
        self._conn.commit()

    def update_paths(
        self,
        record_id: str,
        *,
        audio_path: str | Path | None = None,
        srt_path: str | Path | None = None,
        md_path: str | Path | None = None,
        txt_path: str | Path | None = None,
        raw_json_path: str | Path | None = None,
    ) -> None:
        """지정된 경로 컬럼만 업데이트. 값이 None인 인자는 건너뜀."""
        updates: dict[str, Any] = {}
        if audio_path is not None:
            updates["audio_path"] = str(audio_path)
        if srt_path is not None:
            updates["srt_path"] = str(srt_path)
        if md_path is not None:
            updates["md_path"] = str(md_path)
        if txt_path is not None:
            updates["txt_path"] = str(txt_path)
        if raw_json_path is not None:
            updates["raw_json_path"] = str(raw_json_path)
        if not updates:
            return
        cols = ", ".join(f"{k} = ?" for k in updates)
        self._conn.execute(
            f"UPDATE transcripts SET {cols} WHERE id = ?",
            (*updates.values(), record_id),
        )
        self._conn.commit()

    def complete(
        self,
        record_id: str,
        *,
        result: TranscriptionResult,
        srt_path: str | Path | None = None,
        md_path: str | Path | None = None,
        txt_path: str | Path | None = None,
        raw_json_path: str | Path | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE transcripts SET
                status = 'completed',
                duration_sec = ?,
                speaker_count = ?,
                language = ?,
                model = ?,
                srt_path = ?,
                md_path = ?,
                txt_path = ?,
                raw_json_path = ?,
                transcript_text = ?,
                completed_at = ?
            WHERE id = ?
            """,
            (
                result.duration_sec,
                result.speaker_count,
                result.metadata.language,
                result.metadata.model,
                _s(srt_path),
                _s(md_path),
                _s(txt_path),
                _s(raw_json_path),
                result.plain_text,
                _now(),
                record_id,
            ),
        )
        self._conn.commit()
        logger.info("레코드 완료: %s", record_id)

    def fail(self, record_id: str, error: str) -> None:
        self._conn.execute(
            """
            UPDATE transcripts SET status = 'failed', error = ?, completed_at = ?
            WHERE id = ?
            """,
            (error, _now(), record_id),
        )
        self._conn.commit()
        logger.warning("레코드 실패: %s - %s", record_id, error)

    # ---------- Store Protocol ----------

    def save(self, result: TranscriptionResult, metadata: dict) -> str:
        """라이브러리 사용자 친화 API: 완료된 결과를 한 방에 저장."""
        rec_id = self.create_pending(
            tg_user_id=metadata.get("tg_user_id"),
            tg_username=metadata.get("tg_username"),
            tg_chat_id=metadata.get("tg_chat_id"),
            tg_message_id=metadata.get("tg_message_id"),
            file_name=metadata.get("file_name"),
            file_size_bytes=metadata.get("file_size_bytes"),
            file_format=metadata.get("file_format"),
            caption=metadata.get("caption"),
            session_title=metadata.get("session_title") or metadata.get("title"),
            romanized_slug=metadata.get("romanized_slug") or metadata.get("slug"),
            recording_date=metadata.get("recording_date"),
            place=metadata.get("place"),
            source=metadata.get("source", "library"),
            received_at=metadata.get("received_at"),
        )
        self.complete(
            rec_id,
            result=result,
            srt_path=metadata.get("srt_path"),
            md_path=metadata.get("md_path"),
            txt_path=metadata.get("txt_path"),
            raw_json_path=metadata.get("raw_json_path"),
        )
        if metadata.get("audio_path"):
            self.set_audio_path(rec_id, metadata["audio_path"])
        return rec_id

    def get(self, record_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM transcripts WHERE id = ?", (record_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_recent(self, limit: int = 5, *, tg_user_id: int | None = None) -> list[dict]:
        if tg_user_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM transcripts WHERE tg_user_id = ? ORDER BY created_at DESC LIMIT ?",
                (tg_user_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM transcripts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all(self) -> list[dict]:
        """마이그레이션용: 모든 레코드 반환."""
        rows = self._conn.execute(
            "SELECT * FROM transcripts ORDER BY created_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _s(value: Any) -> str | None:
    return str(value) if value is not None else None


def _date_str(value: date | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


def _dt_str(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat(timespec="seconds")
