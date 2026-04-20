from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from cheroki.config import Config
from cheroki.interfaces.telegram.handlers import router
from cheroki.storage.fs_store import FileStore
from cheroki.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)


def build_bot(config: Config) -> Bot:
    """설정에 따라 Bot 인스턴스 생성. LOCAL_API_URL이 설정되면 로컬 서버를 본다."""
    if config.local_api_url and config.local_api_url.strip():
        server = TelegramAPIServer.from_base(config.local_api_url.rstrip("/"))
        session = AiohttpSession(api=server)
        logger.info("Local Bot API 서버 사용: %s", config.local_api_url)
    else:
        session = AiohttpSession()
        logger.info("클라우드 Bot API 사용 (파일 크기 제한 20MB)")

    return Bot(
        token=config.bot_token,
        session=session,
        default=DefaultBotProperties(),
    )


def build_dispatcher(config: Config, db: SQLiteStore, fs: FileStore) -> Dispatcher:
    dp = Dispatcher()
    dp["config"] = config
    dp["db"] = db
    dp["fs"] = fs
    dp.include_router(router)
    return dp
