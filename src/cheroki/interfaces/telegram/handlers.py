from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message

from cheroki.core.transcribe import transcribe_audio
from cheroki.interfaces.telegram import formatters as fmt

if TYPE_CHECKING:
    from cheroki.config import Config
    from cheroki.storage.fs_store import FileStore
    from cheroki.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)

router = Router(name="cheroki")


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

    rec_id = db.create_pending(
        tg_user_id=message.from_user.id,
        tg_username=message.from_user.username,
        tg_chat_id=message.chat.id,
        tg_message_id=message.message_id,
        file_name=file_name,
        file_size_bytes=file_size,
        caption=caption,
        session_title=caption,
    )

    await message.answer(fmt.received_message(rec_id, file_name, file_size))

    try:
        audio_path = fs.upload_path(rec_id, suffix)
        logger.info("다운로드 시작: %s -> %s", tg_file_id, audio_path)
        await bot.download(tg_file_id, destination=audio_path)
        db.set_audio_path(rec_id, audio_path)
        db.set_processing(rec_id)

        result = await transcribe_audio(audio_path)

        paths = fs.write_exports(rec_id, result, title=caption)
        db.complete(
            rec_id,
            result=result,
            srt_path=paths["srt"],
            md_path=paths["md"],
            txt_path=paths["txt"],
            raw_json_path=paths["raw"],
        )

        await message.answer(fmt.completed_message(rec_id, result, caption=caption))
        for key in ("srt", "md", "txt"):
            await message.answer_document(FSInputFile(paths[key]))
    except Exception as exc:
        logger.exception("처리 실패: %s", rec_id)
        db.fail(rec_id, str(exc))
        await message.answer(fmt.failed_message(rec_id, str(exc)))


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
