from __future__ import annotations

import asyncio
import logging
import sys

from cheroki.config import load_config, setup_logging
from cheroki.interfaces.telegram.bot import build_bot, build_dispatcher
from cheroki.storage.fs_store import FileStore
from cheroki.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)


async def run() -> None:
    config = load_config()
    setup_logging(config.log_level)

    if not config.bot_token:
        logger.error("BOT_TOKEN이 비어 있습니다. .env를 확인하세요.")
        sys.exit(1)
    if not config.deepgram_api_key:
        logger.error("DEEPGRAM_API_KEY가 비어 있습니다. .env를 확인하세요.")
        sys.exit(1)
    if not config.allowed_user_ids:
        logger.warning(
            "ALLOWED_USER_IDS가 비어 있습니다. 모든 메시지가 거부됩니다. "
            ".env에 허용할 Telegram user ID를 추가하세요 (@userinfobot)."
        )

    db = SQLiteStore(config.db_path)
    fs = FileStore(config.data_dir)

    bot = build_bot(config)
    dp = build_dispatcher(config, db, fs)

    me = await bot.get_me()
    logger.info("봇 시작: @%s (id=%s)", me.username, me.id)

    try:
        await dp.start_polling(bot, handle_signals=True)
    finally:
        await bot.session.close()
        db.close()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n중단됨.")


if __name__ == "__main__":
    main()
