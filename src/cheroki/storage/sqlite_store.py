from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cheroki.core.result import TranscriptionResult
from cheroki.storage.ids import generate_short_id

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    id TEXT PRIMARY KEY,
    tg_user_id INTEGER,
    tg_username TEXT,
    tg_chat_id INTEGER,
    tg_message_id INTEGER,
    file_name TEXT,
    file_size_bytes INTEGER,
    caption TEXT,
    session_title TEXT,
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
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tg_user ON transcripts(tg_user_id);
CREATE INDEX IF NOT EXISTS idx_status ON transcripts(status);
CREATE INDEX IF NOT EXISTS idx_created ON transcripts(created_at DESC);
"""


class SQLiteStore:
    """SQLite 기반 transcripts 저장소."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

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
        caption: str | None = None,
        session_title: str | None = None,
    ) -> str:
        """pending 상태로 레코드 생성. short ID 반환. 충돌 시 재시도."""
        for _ in range(10):
            rec_id = generate_short_id()
            try:
                self._conn.execute(
                    """
                    INSERT INTO transcripts (
                        id, tg_user_id, tg_username, tg_chat_id, tg_message_id,
                        file_name, file_size_bytes, caption, session_title,
                        status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        rec_id, tg_user_id, tg_username, tg_chat_id, tg_message_id,
                        file_name, file_size_bytes, caption, session_title,
                        _now(),
                    ),
                )
                self._conn.commit()
                logger.info("레코드 생성: %s (file=%s)", rec_id, file_name)
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

    def set_processing(self, record_id: str) -> None:
        self._conn.execute(
            "UPDATE transcripts SET status = 'processing' WHERE id = ?",
            (record_id,),
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
            caption=metadata.get("caption"),
            session_title=metadata.get("session_title") or metadata.get("title"),
        )
        self.complete(
            rec_id,
            result=result,
            srt_path=metadata.get("srt_path"),
            md_path=metadata.get("md_path"),
            txt_path=metadata.get("txt_path"),
            raw_json_path=metadata.get("raw_json_path"),
        )
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


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _s(value: Any) -> str | None:
    return str(value) if value is not None else None
