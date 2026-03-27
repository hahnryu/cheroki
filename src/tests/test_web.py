"""웹 서버 테스트."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from cheroki.web import create_app, _list_files


@pytest.fixture
def config(tmp_path: Path) -> dict:
    """테스트용 설정."""
    for d in ["originals", "transcripts", "corrections", "corpus", "exports"]:
        (tmp_path / d).mkdir()
    return {
        "paths": {
            "originals": str(tmp_path / "originals"),
            "transcripts": str(tmp_path / "transcripts"),
            "corrections": str(tmp_path / "corrections"),
            "corpus": str(tmp_path / "corpus"),
            "exports": str(tmp_path / "exports"),
        },
        "whisper": {"model": "tiny", "device": "cpu", "compute_type": "int8", "language": "ko"},
    }


@pytest.fixture
def client(config: dict) -> TestClient:
    app = create_app(config)
    return TestClient(app)


class TestStatusAPI:
    def test_status(self, client: TestClient) -> None:
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["whisper_model"] == "tiny"


class TestIndexPage:
    def test_index_renders(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Cheroki" in resp.text


class TestFileListAPI:
    def test_empty_list(self, client: TestClient) -> None:
        resp = client.get("/api/files")
        assert resp.status_code == 200
        assert resp.json()["files"] == []

    def test_with_files(self, config: dict, client: TestClient) -> None:
        originals_dir = Path(config["paths"]["originals"])
        meta = {
            "file_id": "20260101_000000_test",
            "original_name": "test.mp3",
            "stored_at": "2026-01-01T00:00:00",
            "size_bytes": 1234,
        }
        (originals_dir / "20260101_000000_test.meta.json").write_text(
            json.dumps(meta), encoding="utf-8"
        )
        resp = client.get("/api/files")
        files = resp.json()["files"]
        assert len(files) == 1
        assert files[0]["file_id"] == "20260101_000000_test"


class TestUploadAPI:
    def test_upload_no_file(self, client: TestClient) -> None:
        resp = client.post("/api/upload")
        assert resp.status_code == 422

    def test_upload_unsupported_format(self, client: TestClient) -> None:
        resp = client.post(
            "/api/upload",
            files={"file": ("readme.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 400

    def test_upload_success(self, config: dict, client: TestClient) -> None:
        # mock pipeline (lazy import inside handler)
        mock_result = MagicMock()
        mock_result.segments = [MagicMock()]
        mock_result.duration = 10.5
        mock_result.full_text = "테스트 전사 결과"

        with patch("cheroki.pipeline.run_pipeline") as mock_pipeline:
            mock_pipeline.return_value = {
                "file_id": "test_123",
                "result": mock_result,
            }
            resp = client.post(
                "/api/upload",
                files={"file": ("test.mp3", b"\x00" * 100, "audio/mpeg")},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["file_id"] == "test_123"


class TestTranscriptAPI:
    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/transcript/nonexistent")
        assert resp.status_code == 404

    def test_found(self, config: dict, client: TestClient) -> None:
        transcripts_dir = Path(config["paths"]["transcripts"])
        data = {"full_text": "안녕하세요", "segments": []}
        (transcripts_dir / "test_id.transcript.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        resp = client.get("/api/transcript/test_id")
        assert resp.status_code == 200
        assert resp.json()["full_text"] == "안녕하세요"


class TestDownloadAPI:
    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/download/none/srt")
        assert resp.status_code == 404

    def test_bad_format(self, client: TestClient) -> None:
        resp = client.get("/api/download/none/pdf")
        assert resp.status_code == 400

    def test_download_srt(self, config: dict, client: TestClient) -> None:
        exports_dir = Path(config["paths"]["exports"])
        (exports_dir / "test_id.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
        resp = client.get("/api/download/test_id/srt")
        assert resp.status_code == 200


class TestListFiles:
    def test_empty_dir(self, tmp_path: Path) -> None:
        files = _list_files(tmp_path / "orig", tmp_path / "tr", tmp_path / "ex")
        assert files == []

    def test_with_metadata(self, tmp_path: Path) -> None:
        orig = tmp_path / "orig"
        orig.mkdir()
        tr = tmp_path / "tr"
        tr.mkdir()
        ex = tmp_path / "ex"
        ex.mkdir()

        meta = {"file_id": "abc", "original_name": "a.mp3", "stored_at": "2026-01-01", "size_bytes": 100}
        (orig / "abc.meta.json").write_text(json.dumps(meta))
        (tr / "abc.transcript.json").write_text("{}")

        files = _list_files(orig, tr, ex)
        assert len(files) == 1
        assert files[0]["has_transcript"]
        assert not files[0]["has_exports"]
