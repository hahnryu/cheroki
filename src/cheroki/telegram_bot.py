"""텔레그램 봇 모듈 — 음성 파일 수신 및 전사 파이프라인 연동."""

from __future__ import annotations

import asyncio
import structlog
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from cheroki.config import get_config
from cheroki.storage import AUDIO_EXTENSIONS

logger = structlog.get_logger()


class CherokiBot:
    """텔레그램 봇 — 음성 파일을 받아 전사 파이프라인을 실행한다."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        tg_cfg = config.get("telegram", {})
        self.token: str = tg_cfg.get("bot_token", "")
        self.allowed_users: list[int] = tg_cfg.get("allowed_users", [])
        if not self.token:
            raise ValueError("telegram.bot_token이 config.yaml에 설정되지 않았습니다")

    def _is_allowed(self, user_id: int) -> bool:
        """사용자 접근 권한 확인. allowed_users가 비어있으면 모두 허용."""
        if not self.allowed_users:
            return True
        return user_id in self.allowed_users

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """'/start' 명령어 핸들러."""
        if not update.effective_user or not update.message:
            return
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("접근 권한이 없습니다.")
            return
        await update.message.reply_text(
            "안녕하세요! Cheroki 전사 봇입니다.\n"
            "음성 파일을 보내주시면 자동으로 전사합니다.\n\n"
            "명령어:\n"
            "/start — 인사\n"
            "/help — 도움말\n"
            "/status — 상태 확인"
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """'/help' 명령어 핸들러."""
        if not update.message:
            return
        await update.message.reply_text(
            "사용법:\n"
            "1. 음성 파일(mp3, m4a, wav, ogg 등)을 이 채팅에 보내세요.\n"
            "2. 자동으로 전사가 시작됩니다.\n"
            "3. 전사 완료 후 텍스트 결과를 보내드립니다.\n\n"
            "지원 형식: " + ", ".join(sorted(AUDIO_EXTENSIONS))
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """'/status' 명령어 핸들러."""
        if not update.message:
            return
        originals_dir = Path(self.config["paths"]["originals"])
        transcripts_dir = Path(self.config["paths"]["transcripts"])

        n_originals = len(list(originals_dir.glob("*.meta.json"))) if originals_dir.exists() else 0
        n_transcripts = len(list(transcripts_dir.glob("*.transcript.json"))) if transcripts_dir.exists() else 0

        await update.message.reply_text(
            f"Cheroki 상태:\n"
            f"  원본 파일: {n_originals}개\n"
            f"  전사 결과: {n_transcripts}개\n"
            f"  Whisper 모델: {self.config['whisper']['model']}"
        )

    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """음성/오디오 파일 수신 핸들러."""
        if not update.effective_user or not update.message:
            return
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("접근 권한이 없습니다.")
            return

        message = update.message
        file_obj = message.audio or message.voice or message.document
        if not file_obj:
            return

        # 문서인 경우 확장자 확인
        if message.document and message.document.file_name:
            ext = Path(message.document.file_name).suffix.lower()
            if ext not in AUDIO_EXTENSIONS:
                await message.reply_text(f"지원하지 않는 형식입니다: {ext}")
                return

        await message.reply_text("파일 수신 완료. 전사를 시작합니다...")

        try:
            result = await self._download_and_transcribe(file_obj, message, context)
            tr = result["result"]
            file_id = result["file_id"]

            # 타임스탬프 포함 포맷
            text = _format_transcript(tr)
            duration_min = int(tr.duration // 60)
            duration_sec = int(tr.duration % 60)

            header = (
                f"전사 완료 (ID: {file_id})\n"
                f"세그먼트: {len(tr.segments)}개 | "
                f"길이: {duration_min}분 {duration_sec}초\n\n"
                f"--- 결과 ---"
            )

            # 텔레그램 메시지 길이 제한 (4096자)
            if len(header) + len(text) + 2 > 3800:
                await message.reply_text(header)
                for chunk in _split_text(text, 3800):
                    await message.reply_text(chunk)
            else:
                await message.reply_text(f"{header}\n{text}")

            logger.info("telegram_transcription_complete", file_id=file_id)

        except Exception as e:
            logger.error("telegram_transcription_error", error=str(e))
            await message.reply_text(f"전사 중 오류가 발생했습니다: {e}")

    async def _download_and_transcribe(
        self,
        file_obj: Any,
        message: Any,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> dict[str, Any]:
        """파일 다운로드 → originals/ 저장 → 파이프라인 실행."""
        from cheroki.pipeline import run_pipeline

        originals_dir = Path(self.config["paths"]["originals"])
        originals_dir.mkdir(parents=True, exist_ok=True)

        # 파일 다운로드
        tg_file = await context.bot.get_file(file_obj.file_id)

        # 파일 이름 결정
        if hasattr(file_obj, "file_name") and file_obj.file_name:
            filename = file_obj.file_name
        else:
            filename = f"voice_{file_obj.file_unique_id}.ogg"

        download_path = originals_dir / f"tg_{filename}"
        await tg_file.download_to_drive(str(download_path))
        logger.info("telegram_file_downloaded", path=str(download_path))

        # 파이프라인 실행 (동기 함수를 스레드에서)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: run_pipeline(download_path, config=self.config)
        )

        # 다운로드 임시 파일 삭제 (원본은 pipeline이 originals/에 복사함)
        if download_path.exists():
            download_path.unlink()

        return result

    def build_application(self) -> Application:
        """텔레그램 Application 객체를 구성한다."""
        app = Application.builder().token(self.token).build()

        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))

        # 음성, 오디오, 문서(음성 파일) 핸들러
        app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, self.handle_audio))
        app.add_handler(MessageHandler(filters.Document.ALL, self.handle_audio))

        return app

    def run(self) -> None:
        """봇을 실행한다 (polling 모드)."""
        logger.info("telegram_bot_starting")
        app = self.build_application()
        app.run_polling(drop_pending_updates=True)


def _format_timestamp(seconds: float) -> str:
    """초를 MM:SS 형식으로."""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _format_transcript(result: Any) -> str:
    """전사 결과를 타임스탬프+화자 포함 텍스트로 포맷."""
    lines: list[str] = []
    for seg in result.segments:
        ts = _format_timestamp(seg.start)
        speaker = getattr(seg, "speaker", "") or ""
        text = seg.text.strip()
        if speaker:
            lines.append(f"[{ts}] {speaker}: {text}")
        else:
            lines.append(f"[{ts}] {text}")
    return "\n".join(lines)


def _split_text(text: str, max_len: int) -> list[str]:
    """긴 텍스트를 max_len 이하 청크로 분할. 줄바꿈 기준으로 자른다."""
    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # 줄바꿈에서 자르기 (타임스탬프 라인이 중간에 잘리지 않게)
        idx = text.rfind("\n", 0, max_len)
        if idx == -1:
            idx = text.rfind(" ", 0, max_len)
        if idx == -1:
            idx = max_len
        chunks.append(text[:idx])
        text = text[idx:].lstrip()
    return chunks
