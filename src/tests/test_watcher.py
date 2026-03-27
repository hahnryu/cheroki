"""watcher 모듈 테스트."""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

from cheroki.watcher import AudioFileHandler, watch_folder


def test_audio_file_handler_calls_callback():
    cb = MagicMock()
    handler = AudioFileHandler(cb)

    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "test.wav"
        audio.write_bytes(b"RIFF" + b"\x00" * 100)

        from watchdog.events import FileCreatedEvent
        event = FileCreatedEvent(str(audio))
        handler.on_created(event)

        cb.assert_called_once_with(audio)


def test_audio_file_handler_ignores_non_audio():
    cb = MagicMock()
    handler = AudioFileHandler(cb)

    with tempfile.TemporaryDirectory() as tmp:
        txt = Path(tmp) / "notes.txt"
        txt.write_text("hello")

        from watchdog.events import FileCreatedEvent
        event = FileCreatedEvent(str(txt))
        handler.on_created(event)

        cb.assert_not_called()


def test_audio_file_handler_deduplicates():
    cb = MagicMock()
    handler = AudioFileHandler(cb)

    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "test.mp3"
        audio.write_bytes(b"\x00" * 100)

        from watchdog.events import FileCreatedEvent
        event = FileCreatedEvent(str(audio))
        handler.on_created(event)
        handler.on_created(event)

        assert cb.call_count == 1


def test_watch_folder_detects_new_file():
    cb = MagicMock()

    with tempfile.TemporaryDirectory() as tmp:
        watch_dir = Path(tmp) / "incoming"
        watch_dir.mkdir()

        observer = watch_folder(watch_dir, cb, poll_interval=0.5)

        try:
            time.sleep(0.5)  # observer 안정화
            audio = watch_dir / "new_recording.wav"
            audio.write_bytes(b"RIFF" + b"\x00" * 100)
            time.sleep(2.0)  # 이벤트 전파 대기
        finally:
            observer.stop()
            observer.join(timeout=3)

        assert cb.call_count >= 1
        called_path = cb.call_args[0][0]
        assert called_path.name == "new_recording.wav"
