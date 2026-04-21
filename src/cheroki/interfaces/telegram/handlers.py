from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message

from cheroki.core.transcribe import transcribe_audio
from cheroki.interfaces.telegram import formatters as fmt
from cheroki.naming import (
    build_slug,
    file_format_from_name,
    parse_recording_date,
)

if TYPE_CHECKING:
    from cheroki.config import Config
    from cheroki.storage.fs_store import FileStore
    from cheroki.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)

router = Router(name="cheroki")

_TICK_INTERVAL_SEC = 7.0


async def _safe_edit(msg: Message, text: str) -> None:
    """같은 내용으로 edit하면 Telegram이 400을 주므로 조용히 삼킨다."""
    try:
        await msg.edit_text(text)
    except TelegramBadRequest:
        pass


@asynccontextmanager
async def _status_tick(msg: Message, label_fn: Callable[[float], str]):
    """긴 await 동안 status 메시지를 주기적으로 갱신한다.

    label_fn(elapsed_sec)이 edit할 텍스트를 돌려준다.
    """
    start = time.monotonic()

    async def _loop() -> None:
        while True:
            await asyncio.sleep(_TICK_INTERVAL_SEC)
            elapsed = time.monotonic() - start
            await _safe_edit(msg, label_fn(elapsed))

    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def _media_duration(message: Message) -> int | None:
    for obj in (message.audio, message.voice, message.video, message.video_note):
        if obj is not None and getattr(obj, "duration", None):
            return int(obj.duration)
    return None


def _storage_rel_path(audio_path: Path, data_dir: Path) -> str:
    """DATA_DIR 기준 상대 경로. 'data/260421/<slug>_raw.m4a' 같은 형태."""
    try:
        rel = audio_path.relative_to(data_dir)
    except ValueError:
        return str(audio_path)
    return f"{data_dir.name}/{rel}"


def _is_allowed(message: Message, config: Config) -> bool:
    if not config.allowed_user_ids:
        return False
    if message.from_user is None:
        return False
    return message.from_user.id in config.allowed_user_ids


@router.message(CommandStart())
async def cmd_start(message: Message, config: Config) -> None:
    if not _is_allowed(message, config):
        await message.answer(fmt.not_allowed_message())
        return
    await message.answer(fmt.welcome_message())


@router.message(Command("help"))
async def cmd_help(message: Message, config: Config) -> None:
    if not _is_allowed(message, config):
        await message.answer(fmt.not_allowed_message())
        return
    await message.answer(fmt.help_message())


@router.message(Command("last"))
async def cmd_last(message: Message, config: Config, db: SQLiteStore) -> None:
    if not _is_allowed(message, config):
        await message.answer(fmt.not_allowed_message())
        return
    records = db.list_recent(limit=5, tg_user_id=message.from_user.id)
    await message.answer(fmt.list_recent_message(records))


@router.message(Command("status"))
async def cmd_status(message: Message, config: Config, db: SQLiteStore) -> None:
    if not _is_allowed(message, config):
        await message.answer(fmt.not_allowed_message())
        return
    rec_id = _parse_id_arg(message.text)
    if not rec_id:
        await message.answer("사용법: /status <id>")
        return
    record = db.get(rec_id)
    if not record:
        await message.answer(fmt.record_not_found_message(rec_id))
        return
    await message.answer(fmt.status_message(record))


@router.message(Command("get"))
async def cmd_get(
    message: Message,
    bot: Bot,
    config: Config,
    db: SQLiteStore,
) -> None:
    if not _is_allowed(message, config):
        await message.answer(fmt.not_allowed_message())
        return
    rec_id = _parse_id_arg(message.text)
    if not rec_id:
        await message.answer("사용법: /get <id>")
        return
    record = db.get(rec_id)
    if not record:
        await message.answer(fmt.record_not_found_message(rec_id))
        return
    if record.get("status") != "completed":
        await message.answer(fmt.record_not_completed_message(rec_id, record.get("status") or "?"))
        return
    await _send_exports(message, record)


@router.message(F.audio | F.voice | F.video | F.video_note | F.document)
async def handle_media(
    message: Message,
    bot: Bot,
    config: Config,
    db: SQLiteStore,
    fs: FileStore,
) -> None:
    if not _is_allowed(message, config):
        await message.answer(fmt.not_allowed_message())
        return

    media = _extract_media(message)
    if media is None:
        await message.answer("오디오/비디오 파일을 보내주세요.")
        return

    tg_file_id, file_name, file_size, suffix = media
    caption = message.caption
    received_at = message.date or datetime.now(UTC)

    recording_date = parse_recording_date(caption, fallback=received_at)
    file_format = file_format_from_name(file_name) or suffix

    # 레코드 먼저 생성 (short ID 확보)
    rec_id = db.create_pending(
        tg_user_id=message.from_user.id,
        tg_username=message.from_user.username,
        tg_chat_id=message.chat.id,
        tg_message_id=message.message_id,
        file_name=file_name,
        file_size_bytes=file_size,
        file_format=file_format,
        caption=caption,
        session_title=caption,
        recording_date=recording_date,
        source="telegram",
        received_at=received_at,
    )

    # 슬러그 계산 (ID를 fallback으로 쓰기 위해 이 시점)
    slug = build_slug(caption=caption, original_filename=file_name, record_id=rec_id)
    db.set_slug(rec_id, slug)

    audio_path = fs.audio_path(recording_date, slug, suffix)

    # 1) 받음 알림: 메타와 저장 경로를 바로 보여준다.
    await message.answer(
        fmt.received_message(
            rec_id,
            file_name,
            file_size,
            duration_sec=_media_duration(message),
            storage_rel_path=_storage_rel_path(audio_path, config.data_dir),
        )
    )

    # 2) 상태 메시지 하나를 edit 방식으로 이어간다. 채팅이 지저분해지지 않도록.
    status_msg = await message.answer(fmt.status_downloading())

    try:
        logger.info("다운로드 시작: %s -> %s", tg_file_id, audio_path)
        t0 = time.monotonic()
        async with _status_tick(status_msg, fmt.status_downloading):
            await bot.download(tg_file_id, destination=audio_path)
        await _safe_edit(status_msg, fmt.status_downloaded(time.monotonic() - t0))

        db.set_audio_path(rec_id, audio_path)
        db.set_processing(rec_id)

        await _safe_edit(status_msg, fmt.status_transcribing())
        t0 = time.monotonic()
        async with _status_tick(status_msg, fmt.status_transcribing):
            result = await transcribe_audio(audio_path)
        transcribe_elapsed = time.monotonic() - t0
        await _safe_edit(status_msg, fmt.status_transcribed(transcribe_elapsed, result))

        await _safe_edit(status_msg, fmt.status_exporting())
        frontmatter = _build_frontmatter(
            rec_id=rec_id,
            slug=slug,
            recording_date=recording_date.isoformat(),
            caption=caption,
            file_name=file_name,
            file_format=file_format,
            received_at=received_at,
        )
        paths = fs.write_exports(recording_date, slug, result, frontmatter_extra=frontmatter)
        db.complete(
            rec_id,
            result=result,
            srt_path=paths["srt"],
            md_path=paths["md"],
            txt_path=paths["txt"],
            raw_json_path=paths["raw"],
        )

        await _safe_edit(status_msg, fmt.status_sending())
        await message.answer(fmt.completed_message(rec_id, result, caption=caption))
        for key in ("srt", "md", "txt"):
            await message.answer_document(FSInputFile(paths[key]))
        await _safe_edit(status_msg, fmt.status_all_done())
    except Exception as exc:
        logger.exception("처리 실패: %s", rec_id)
        db.fail(rec_id, str(exc))
        await _safe_edit(status_msg, fmt.status_all_done())
        await message.answer(fmt.failed_message(rec_id, str(exc)))


def _build_frontmatter(
    *,
    rec_id: str,
    slug: str,
    recording_date: str,
    caption: str | None,
    file_name: str | None,
    file_format: str | None,
    received_at: datetime,
) -> dict:
    title = caption or file_name or slug
    return {
        "title": title,
        "recording_date": recording_date,
        "record_id": rec_id,
        "slug": slug,
        "source": "telegram",
        "caption": caption,
        "original_filename": file_name,
        "file_format": file_format,
        "received_at": received_at.isoformat(timespec="seconds"),
    }


async def _send_exports(message: Message, record: dict) -> None:
    paths = {
        "srt": record.get("srt_path"),
        "md": record.get("md_path"),
        "txt": record.get("txt_path"),
    }
    sent_any = False
    for path in paths.values():
        if path and Path(path).exists():
            await message.answer_document(FSInputFile(path))
            sent_any = True
    if not sent_any:
        await message.answer("저장된 산출물 파일을 찾을 수 없습니다.")


def _parse_id_arg(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[1].strip().lower()


def _extract_media(message: Message) -> tuple[str, str | None, int | None, str] | None:
    """메시지에서 오디오/비디오 파일 정보 추출. (file_id, file_name, size, suffix)."""
    if message.audio:
        a = message.audio
        name = a.file_name or f"audio.{(a.mime_type or 'audio/mp4').split('/')[-1]}"
        return a.file_id, name, a.file_size, Path(name).suffix or ".m4a"
    if message.voice:
        v = message.voice
        return v.file_id, f"voice_{message.message_id}.ogg", v.file_size, ".ogg"
    if message.video:
        v = message.video
        name = v.file_name or f"video_{message.message_id}.mp4"
        return v.file_id, name, v.file_size, Path(name).suffix or ".mp4"
    if message.video_note:
        vn = message.video_note
        return vn.file_id, f"videonote_{message.message_id}.mp4", vn.file_size, ".mp4"
    if message.document:
        d = message.document
        mime = d.mime_type or ""
        if not (mime.startswith("audio/") or mime.startswith("video/")):
            return None
        name = d.file_name or f"doc_{message.message_id}"
        return d.file_id, name, d.file_size, Path(name).suffix or ".bin"
    return None
