from __future__ import annotations

import json
from datetime import date

from cheroki.core.result import TranscriptionResult
from cheroki.storage.fs_store import FileStore
from cheroki.storage.sqlite_store import SQLiteStore


def test_sqlite_pending_complete(tmp_path, sample_utterances, sample_metadata):
    db = SQLiteStore(tmp_path / "test.db")
    rec_id = db.create_pending(
        tg_user_id=123,
        tg_username="tester",
        tg_chat_id=456,
        tg_message_id=789,
        file_name="sample.m4a",
        file_size_bytes=1024,
        file_format=".m4a",
        caption="테스트 260420 하회",
        session_title="테스트 260420 하회",
        romanized_slug="teseuteu_hahoe",
        recording_date=date(2026, 4, 20),
        source="telegram",
    )
    assert len(rec_id) == 6

    got = db.get(rec_id)
    assert got is not None
    assert got["status"] == "pending"
    assert got["tg_user_id"] == 123
    assert got["file_format"] == ".m4a"
    assert got["romanized_slug"] == "teseuteu_hahoe"
    assert got["recording_date"] == "2026-04-20"
    assert got["source"] == "telegram"

    result = TranscriptionResult(utterances=sample_utterances, metadata=sample_metadata)
    db.set_processing(rec_id)
    db.complete(rec_id, result=result, srt_path="/tmp/a.srt", md_path="/tmp/a.md")

    got = db.get(rec_id)
    assert got["status"] == "completed"
    assert got["duration_sec"] == 12.5
    assert got["speaker_count"] == 2
    assert "안녕하세요" in got["transcript_text"]
    db.close()


def test_sqlite_set_slug(tmp_path):
    db = SQLiteStore(tmp_path / "test.db")
    rec_id = db.create_pending(file_name="x.m4a")
    assert db.get(rec_id)["romanized_slug"] is None
    db.set_slug(rec_id, "my_slug")
    assert db.get(rec_id)["romanized_slug"] == "my_slug"
    db.close()


def test_sqlite_update_paths(tmp_path):
    db = SQLiteStore(tmp_path / "test.db")
    rec_id = db.create_pending(file_name="x.m4a")
    db.update_paths(rec_id, srt_path="/tmp/foo.srt", md_path="/tmp/foo.md")
    got = db.get(rec_id)
    assert got["srt_path"] == "/tmp/foo.srt"
    assert got["md_path"] == "/tmp/foo.md"
    assert got["txt_path"] is None
    db.close()


def test_sqlite_fail(tmp_path):
    db = SQLiteStore(tmp_path / "test.db")
    rec_id = db.create_pending(file_name="x.m4a")
    db.fail(rec_id, "Deepgram 타임아웃")
    got = db.get(rec_id)
    assert got["status"] == "failed"
    assert got["error"] == "Deepgram 타임아웃"
    db.close()


def test_sqlite_list_recent(tmp_path):
    db = SQLiteStore(tmp_path / "test.db")
    for i in range(3):
        db.create_pending(tg_user_id=1, file_name=f"a{i}.m4a")
    db.create_pending(tg_user_id=2, file_name="other.m4a")

    all_recent = db.list_recent(limit=10)
    assert len(all_recent) == 4

    user1 = db.list_recent(limit=10, tg_user_id=1)
    assert len(user1) == 3
    assert all(r["tg_user_id"] == 1 for r in user1)
    db.close()


def test_sqlite_list_all(tmp_path):
    db = SQLiteStore(tmp_path / "test.db")
    db.create_pending(file_name="a.m4a")
    db.create_pending(file_name="b.m4a")
    assert len(db.list_all()) == 2
    db.close()


def test_sqlite_save_oneshot(tmp_path, sample_utterances, sample_metadata):
    db = SQLiteStore(tmp_path / "test.db")
    result = TranscriptionResult(utterances=sample_utterances, metadata=sample_metadata)
    rec_id = db.save(result, {
        "tg_user_id": 42,
        "file_name": "live.m4a",
        "session_title": "점심 대화",
        "audio_path": "/tmp/live.m4a",
        "recording_date": "2026-04-20",
    })
    got = db.get(rec_id)
    assert got["status"] == "completed"
    assert got["session_title"] == "점심 대화"
    assert got["audio_path"] == "/tmp/live.m4a"
    assert got["recording_date"] == "2026-04-20"
    db.close()


def test_sqlite_schema_migration_from_v0(tmp_path):
    """기존 v0 DB 파일(새 컬럼 없음)을 열 때 자동 ALTER."""
    import sqlite3
    p = tmp_path / "legacy.db"
    conn = sqlite3.connect(p)
    conn.executescript(
        """CREATE TABLE transcripts (
               id TEXT PRIMARY KEY, tg_user_id INTEGER, file_name TEXT,
               status TEXT NOT NULL, created_at TEXT NOT NULL);"""
    )
    conn.execute(
        "INSERT INTO transcripts (id, status, created_at) VALUES ('abc123', 'completed', '2026-04-20')"
    )
    conn.commit()
    conn.close()

    db = SQLiteStore(p)
    got = db.get("abc123")
    # 새 컬럼들이 None으로 존재해야 함
    assert got is not None
    assert got["status"] == "completed"
    assert "recording_date" in got
    assert got["recording_date"] is None
    assert "romanized_slug" in got
    db.close()


def test_filestore_new_layout(tmp_path, sample_utterances, sample_metadata):
    fs = FileStore(tmp_path)
    result = TranscriptionResult(
        utterances=sample_utterances,
        metadata=sample_metadata,
        raw_response={"request_id": "abc"},
    )
    d = date(2026, 4, 20)
    slug = "abeonim_morning_walk"
    paths = fs.write_exports(d, slug, result, frontmatter_extra={
        "title": "아버님 morning walk",
        "recording_date": "2026-04-20",
        "record_id": "ab7f3c",
    })

    # 새 레이아웃: tmp_path/260420/abeonim_morning_walk_raw.{srt,md,txt,json}
    session = tmp_path / "260420"
    assert paths["srt"] == session / "abeonim_morning_walk_raw.srt"
    assert paths["md"] == session / "abeonim_morning_walk_raw.md"
    assert paths["txt"] == session / "abeonim_morning_walk_raw.txt"
    assert paths["raw"] == session / "abeonim_morning_walk_raw.json"

    for p in paths.values():
        assert p.exists()

    md_text = paths["md"].read_text(encoding="utf-8")
    assert "title:" in md_text
    assert "recording_date: 2026-04-20" in md_text
    assert "record_id: ab7f3c" in md_text

    raw = json.loads(paths["raw"].read_text(encoding="utf-8"))
    assert raw["request_id"] == "abc"


def test_filestore_audio_path(tmp_path):
    fs = FileStore(tmp_path)
    d = date(2026, 4, 20)
    p1 = fs.audio_path(d, "abeonim_walk", ".m4a")
    p2 = fs.audio_path(d, "abeonim_walk", "mp3")  # 점 없어도 붙여줌
    assert p1.name == "abeonim_walk_raw.m4a"
    assert p2.name == "abeonim_walk_raw.mp3"
    assert p1.parent == tmp_path / "260420"
