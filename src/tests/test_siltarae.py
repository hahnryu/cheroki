"""Siltarae 연동 테스트."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from cheroki.transcriber import TranscriptionResult, Segment
from cheroki.siltarae import (
    Fragment,
    transcription_to_fragments,
    save_fragments,
    SiltaraeClient,
)


@pytest.fixture
def sample_result() -> TranscriptionResult:
    """테스트용 전사 결과."""
    return TranscriptionResult(
        source_file="test.mp3",
        language="ko",
        language_probability=0.99,
        duration=30.0,
        segments=[
            Segment(start=0.0, end=5.0, text="안녕하세요", confidence=0.95),
            Segment(start=5.0, end=10.0, text="반갑습니다", confidence=0.88),
            Segment(start=10.0, end=15.0, text="감사합니다", confidence=0.92),
        ],
    )


@pytest.fixture
def config(tmp_path: Path) -> dict:
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


class TestFragment:
    def test_to_dict(self) -> None:
        f = Fragment(source_id="test", text="hello", start_time=1.0, end_time=2.0)
        d = f.to_dict()
        assert d["source_id"] == "test"
        assert d["text"] == "hello"
        assert d["source_type"] == "audio_transcription"
        assert d["created_at"]  # 자동 생성

    def test_created_at_auto(self) -> None:
        f = Fragment(source_id="test")
        assert f.created_at  # 비어있지 않음


class TestTranscriptionToFragments:
    def test_basic(self, sample_result: TranscriptionResult) -> None:
        frags = transcription_to_fragments(sample_result, "file_001")
        assert len(frags) == 3
        assert frags[0].text == "안녕하세요"
        assert frags[0].source_id == "file_001"
        assert frags[0].start_time == 0.0
        assert frags[0].end_time == 5.0
        assert frags[0].metadata["confidence"] == 0.95
        assert frags[0].metadata["language"] == "ko"

    def test_with_metadata(self, sample_result: TranscriptionResult) -> None:
        frags = transcription_to_fragments(
            sample_result, "file_001", metadata={"topic": "인사"}
        )
        assert frags[0].metadata["topic"] == "인사"

    def test_empty_segments(self) -> None:
        result = TranscriptionResult(
            source_file="empty.mp3", language="ko",
            language_probability=0.5, duration=0.0, segments=[],
        )
        frags = transcription_to_fragments(result, "empty")
        assert frags == []


class TestSaveFragments:
    def test_save(self, sample_result: TranscriptionResult, tmp_path: Path) -> None:
        frags = transcription_to_fragments(sample_result, "test_001")
        path = save_fragments(frags, tmp_path, "test_001")
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 3
        assert data[0]["text"] == "안녕하세요"


class TestSiltaraeClient:
    def test_local_fallback(self, config: dict, sample_result: TranscriptionResult) -> None:
        """API 미설정 시 로컬 저장."""
        client = SiltaraeClient(config)
        result = client.send(sample_result, "test_001")
        assert result["status"] == "local"
        assert result["fragment_count"] == 3
        assert Path(result["path"]).exists()

    def test_with_api_url(self, config: dict, sample_result: TranscriptionResult) -> None:
        """API 설정 시 HTTP 전송 시뮬레이션."""
        config["siltarae"] = {"api_url": "http://localhost:9999/fragments", "api_key": "test"}
        client = SiltaraeClient(config)

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.send(sample_result, "test_001")
        assert result["status"] == "sent"
        assert result["fragment_count"] == 3

    def test_http_error_fallback(self, config: dict, sample_result: TranscriptionResult) -> None:
        """HTTP 오류 시 로컬 저장 fallback."""
        import urllib.error
        config["siltarae"] = {"api_url": "http://localhost:9999/fragments"}
        client = SiltaraeClient(config)

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            result = client.send(sample_result, "test_001")
        assert result["status"] == "error_fallback_local"
        assert Path(result["path"]).exists()
