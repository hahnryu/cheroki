from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import SimpleFilesPathWrapper, TelegramAPIServer

from cheroki.config import Config
from cheroki.interfaces.telegram.handlers import router
from cheroki.storage.fs_store import FileStore
from cheroki.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)

# telegram-bot-api 컨테이너 내부에서 파일을 저장하는 경로.
# docker-compose.yml의 --dir 값과 일치해야 한다.
_CONTAINER_FILES_DIR = Path("/var/lib/telegram-bot-api")


def build_bot(config: Config) -> Bot:
    """설정에 따라 Bot 인스턴스 생성.

    LOCAL_API_URL이 비어 있으면 클라우드 Bot API (20MB 제한).
    설정돼 있으면 Local Bot API Server 사용 (2GB 제한).
      LOCAL_API_FILES_DIR이 같이 있으면 local 모드 경로 매핑도 활성화
      (서버가 주는 컨테이너 내부 경로를 봇 호스트 경로로 변환).
    """
    if not (config.local_api_url and config.local_api_url.strip()):
        session = AiohttpSession()
        logger.info("클라우드 Bot API 사용 (파일 크기 제한 20MB)")
        return Bot(token=config.bot_token, session=session, default=DefaultBotProperties())

    kwargs: dict = {"is_local": True}
    if config.local_api_files_dir:
        host_path = Path(config.local_api_files_dir).expanduser().resolve()
        kwargs["wrap_local_file"] = SimpleFilesPathWrapper(
            server_path=_CONTAINER_FILES_DIR,
            local_path=host_path,
        )
        logger.info(
            "Local Bot API 서버 사용: %s (files: %s ↔ %s)",
            config.local_api_url,
            _CONTAINER_FILES_DIR,
            host_path,
        )
    else:
        logger.info(
            "Local Bot API 서버 사용: %s (경로 매핑 없음 - 같은 FS 가정)",
            config.local_api_url,
        )

    server = TelegramAPIServer.from_base(config.local_api_url.rstrip("/"), **kwargs)
    session = AiohttpSession(api=server)

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
