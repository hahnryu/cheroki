"""텔레그램 봇 테스트."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from cheroki.telegram_bot import CherokiBot, _split_text


@pytest.fixture
def config(tmp_path: Path) -> dict:
    """테스트용 설정."""
    return {
        "paths": {
            "originals": str(tmp_path / "originals"),
            "transcripts": str(tmp_path / "transcripts"),
            "corrections": str(tmp_path / "corrections"),
            "corpus": str(tmp_path / "corpus"),
            "exports": str(tmp_path / "exports"),
        },
        "whisper": {"model": "tiny", "device": "cpu", "compute_type": "int8", "language": "ko", "mode": "local"},
        "telegram": {
            "bot_token": "1234567890:AAFakeTokenForTesting",
            "allowed_users": [],
        },
    }


@pytest.fixture
def bot(config: dict) -> CherokiBot:
    return CherokiBot(config)


class TestCherokiBotInit:
    def test_init_success(self, config: dict) -> None:
        bot = CherokiBot(config)
        assert bot.token == "1234567890:AAFakeTokenForTesting"
        assert bot.allowed_users == []

    def test_init_no_token(self, config: dict) -> None:
        config["telegram"]["bot_token"] = ""
        with pytest.raises(ValueError, match="bot_token"):
            CherokiBot(config)

    def test_init_no_telegram_section(self, config: dict) -> None:
        del config["telegram"]
        with pytest.raises(ValueError, match="bot_token"):
            CherokiBot(config)


class TestAccessControl:
    def test_allow_all_when_empty(self, bot: CherokiBot) -> None:
        assert bot._is_allowed(12345)
        assert bot._is_allowed(99999)

    def test_restrict_when_set(self, config: dict) -> None:
        config["telegram"]["allowed_users"] = [111, 222]
        bot = CherokiBot(config)
        assert bot._is_allowed(111)
        assert bot._is_allowed(222)
        assert not bot._is_allowed(333)


class TestCommandHandlers:
    @pytest.mark.asyncio
    async def test_cmd_start(self, bot: CherokiBot) -> None:
        update = MagicMock()
        update.effective_user.id = 1
        update.message.reply_text = AsyncMock()
        ctx = MagicMock()

        await bot.cmd_start(update, ctx)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Cheroki" in text

    @pytest.mark.asyncio
    async def test_cmd_start_denied(self, config: dict) -> None:
        config["telegram"]["allowed_users"] = [999]
        bot = CherokiBot(config)

        update = MagicMock()
        update.effective_user.id = 1
        update.message.reply_text = AsyncMock()

        await bot.cmd_start(update, MagicMock())
        text = update.message.reply_text.call_args[0][0]
        assert "권한" in text

    @pytest.mark.asyncio
    async def test_cmd_help(self, bot: CherokiBot) -> None:
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        await bot.cmd_help(update, MagicMock())
        text = update.message.reply_text.call_args[0][0]
        assert "음성 파일" in text

    @pytest.mark.asyncio
    async def test_cmd_status(self, bot: CherokiBot, tmp_path: Path) -> None:
        (tmp_path / "originals").mkdir()
        (tmp_path / "transcripts").mkdir()
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        await bot.cmd_status(update, MagicMock())
        text = update.message.reply_text.call_args[0][0]
        assert "원본" in text


class TestHandleAudio:
    @pytest.mark.asyncio
    async def test_unsupported_document(self, bot: CherokiBot) -> None:
        update = MagicMock()
        update.effective_user.id = 1
        update.message.audio = None
        update.message.voice = None
        update.message.document.file_name = "readme.txt"
        update.message.reply_text = AsyncMock()

        await bot.handle_audio(update, MagicMock())
        text = update.message.reply_text.call_args[0][0]
        assert "지원하지 않는" in text

    @pytest.mark.asyncio
    async def test_denied_user(self, config: dict) -> None:
        config["telegram"]["allowed_users"] = [999]
        bot = CherokiBot(config)

        update = MagicMock()
        update.effective_user.id = 1
        update.message.audio = MagicMock()
        update.message.voice = None
        update.message.document = None
        update.message.reply_text = AsyncMock()

        await bot.handle_audio(update, MagicMock())
        text = update.message.reply_text.call_args[0][0]
        assert "권한" in text


class TestBuildApplication:
    def test_build_registers_handlers(self, bot: CherokiBot) -> None:
        app = bot.build_application()
        # CommandHandler 9개 + ConversationHandler 1개 + MessageHandler 2개 = 12개
        assert len(app.handlers[0]) == 12


class TestSplitText:
    def test_short_text(self) -> None:
        assert _split_text("hello", 100) == ["hello"]

    def test_long_text(self) -> None:
        text = "word " * 100  # 500 chars
        chunks = _split_text(text.strip(), 50)
        assert all(len(c) <= 50 for c in chunks)
        assert " ".join(chunks) == text.strip()

    def test_empty(self) -> None:
        assert _split_text("", 100) == []
