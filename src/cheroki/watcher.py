"""폴더 감시 모듈 — 새 음성 파일 감지 시 전사 파이프라인 실행."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import structlog
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

from cheroki.storage import AUDIO_EXTENSIONS

logger = structlog.get_logger()


class AudioFileHandler(FileSystemEventHandler):
    """새 음성 파일 생성 시 콜백을 실행."""

    def __init__(self, callback: Callable[[Path], Any]) -> None:
        super().__init__()
        self.callback = callback
        self._processed: set[str] = set()

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return

        path = Path(event.src_path)
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            return

        # 중복 방지
        abs_path = str(path.resolve())
        if abs_path in self._processed:
            return
        self._processed.add(abs_path)

        logger.info("watcher_file_detected", file=str(path))
        try:
            self.callback(path)
        except Exception:
            logger.exception("watcher_callback_error", file=str(path))


def watch_folder(
    watch_dir: Path,
    callback: Callable[[Path], Any],
    poll_interval: float = 1.0,
) -> Observer:
    """폴더를 감시하고 새 음성 파일이 나타나면 callback을 실행한다.

    Returns:
        Observer 인스턴스 (stop()으로 종료).
    """
    watch_dir = Path(watch_dir)
    watch_dir.mkdir(parents=True, exist_ok=True)

    handler = AudioFileHandler(callback)
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)
    observer.start()

    logger.info("watcher_started", directory=str(watch_dir))
    return observer
