"""환경변수 로딩. .env가 있으면 자동으로 읽어 os.environ에 주입한다."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_DOTENV_LOADED = False


def _ensure_dotenv() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    load_dotenv()
    _DOTENV_LOADED = True


@dataclass(slots=True)
class Config:
    bot_token: str
    telegram_api_id: str
    telegram_api_hash: str
    local_api_url: str
    local_api_files_dir: str

    deepgram_api_key: str
    deepgram_model: str

    elevenlabs_api_key: str
    elevenlabs_model: str

    stt_provider: str

    allowed_user_ids: frozenset[int]

    data_dir: Path
    db_path: Path
    uploads_dir: Path = field(init=False)
    exports_dir: Path = field(init=False)

    log_level: str

    def __post_init__(self) -> None:
        self.uploads_dir = self.data_dir / "uploads"
        self.exports_dir = self.data_dir / "exports"


def load_config() -> Config:
    _ensure_dotenv()

    data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    db_path = Path(os.environ.get("DB_PATH", str(data_dir / "siltare.db"))).resolve()

    allowed_raw = os.environ.get("ALLOWED_USER_IDS", "")
    allowed_ids = frozenset(
        int(x.strip()) for x in allowed_raw.split(",") if x.strip().isdigit()
    )

    return Config(
        bot_token=os.environ.get("BOT_TOKEN", ""),
        telegram_api_id=os.environ.get("TELEGRAM_API_ID", ""),
        telegram_api_hash=os.environ.get("TELEGRAM_API_HASH", ""),
        local_api_url=os.environ.get("LOCAL_API_URL", "http://localhost:8081"),
        local_api_files_dir=os.environ.get("LOCAL_API_FILES_DIR", "").strip(),
        deepgram_api_key=os.environ.get("DEEPGRAM_API_KEY", ""),
        deepgram_model=os.environ.get("DEEPGRAM_MODEL", "nova-2"),
        elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY", ""),
        elevenlabs_model=os.environ.get("ELEVENLABS_MODEL", "scribe_v2"),
        stt_provider=os.environ.get("STT_PROVIDER", "scribe").strip().lower(),
        allowed_user_ids=allowed_ids,
        data_dir=data_dir,
        db_path=db_path,
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
