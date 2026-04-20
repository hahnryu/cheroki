from __future__ import annotations

import json

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
        caption="테스트",
    )
    assert len(rec_id) == 6

    got = db.get(rec_id)
    assert got is not None
    assert got["status"] == "pending"
    assert got["tg_user_id"] == 123
    assert got["caption"] == "테스트"

    result = TranscriptionResult(utterances=sample_utterances, metadata=sample_metadata)
    db.set_processing(rec_id)
    db.complete(rec_id, result=result, srt_path="/tmp/a.srt", md_path="/tmp/a.md")

    got = db.get(rec_id)
    assert got["status"] == "completed"
    assert got["duration_sec"] == 12.5
    assert got["speaker_count"] == 2
    assert "안녕하세요" in got["transcript_text"]
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
    ids = [db.create_pending(tg_user_id=1, file_name=f"a{i}.m4a") for i in range(3)]
    ids += [db.create_pending(tg_user_id=2, file_name="other.m4a")]

    all_recent = db.list_recent(limit=10)
    assert len(all_recent) == 4

    user1 = db.list_recent(limit=10, tg_user_id=1)
    assert len(user1) == 3
    assert all(r["tg_user_id"] == 1 for r in user1)
    db.close()


def test_sqlite_save_oneshot(tmp_path, sample_utterances, sample_metadata):
    db = SQLiteStore(tmp_path / "test.db")
    result = TranscriptionResult(utterances=sample_utterances, metadata=sample_metadata)
    rec_id = db.save(result, {
        "tg_user_id": 42,
        "file_name": "live.m4a",
        "session_title": "점심 대화",
    })
    got = db.get(rec_id)
    assert got["status"] == "completed"
    assert got["session_title"] == "점심 대화"
    db.close()


def test_filestore_write_exports(tmp_path, sample_utterances, sample_metadata):
    fs = FileStore(tmp_path)
    result = TranscriptionResult(
        utterances=sample_utterances,
        metadata=sample_metadata,
        raw_response={"request_id": "abc"},
    )
    paths = fs.write_exports("testid", result, title="t")

    assert paths["srt"].exists()
    assert paths["md"].exists()
    assert paths["txt"].exists()
    assert paths["raw"].exists()

    srt_text = paths["srt"].read_text(encoding="utf-8")
    assert "-->" in srt_text

    raw = json.loads(paths["raw"].read_text(encoding="utf-8"))
    assert raw["request_id"] == "abc"


def test_filestore_upload_path(tmp_path):
    fs = FileStore(tmp_path)
    p1 = fs.upload_path("abc123", ".m4a")
    p2 = fs.upload_path("abc123", "mp3")  # 점 없어도 붙여줌
    assert p1.name == "abc123.m4a"
    assert p2.name == "abc123.mp3"
