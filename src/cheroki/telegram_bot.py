"""텔레그램 봇 모듈 — 음성 전사 + AI 교정 플로우."""

from __future__ import annotations

import asyncio
import json
import structlog
from pathlib import Path
from typing import Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from cheroki.config import get_config
from cheroki.storage import AUDIO_EXTENSIONS

logger = structlog.get_logger()

# 대화 상태
REVIEWING = 1


class CherokiBot:
    """텔레그램 봇 — 음성 전사 + 교정 플로우."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        tg_cfg = config.get("telegram", {})
        self.token: str = tg_cfg.get("bot_token", "")
        self.allowed_users: list[int] = tg_cfg.get("allowed_users", [])
        if not self.token:
            raise ValueError("telegram.bot_token이 config.yaml에 설정되지 않았습니다")

    def _is_allowed(self, user_id: int) -> bool:
        if not self.allowed_users:
            return True
        return user_id in self.allowed_users

    # ── 명령어 ──────────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("접근 권한이 없습니다.")
            return
        await update.message.reply_text(
            "안녕하세요! Cheroki 전사 봇입니다.\n"
            "음성 파일을 보내주시면 전사 + AI 교정까지 진행합니다.\n\n"
            "명령어:\n"
            "/start — 인사\n"
            "/help — 도움말\n"
            "/status — 상태 확인\n"
            "/skip — 교정 건너뛰기"
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        await update.message.reply_text(
            "사용법:\n"
            "1. 음성 파일을 보내세요\n"
            "2. 전사 완료 후 AI가 의심 구간을 질문합니다\n"
            "3. 교정 답변을 보내거나, 맞으면 '확인' 버튼을 누르세요\n"
            "4. /skip 으로 나머지 교정을 건너뛸 수 있습니다\n"
            "5. 교정 완료 후 최종본이 생성됩니다\n\n"
            "지원 형식: " + ", ".join(sorted(AUDIO_EXTENSIONS))
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        originals_dir = Path(self.config["paths"]["originals"])
        transcripts_dir = Path(self.config["paths"]["transcripts"])
        n_originals = len(list(originals_dir.glob("*.meta.json"))) if originals_dir.exists() else 0
        n_transcripts = len(list(transcripts_dir.glob("*.transcript.json"))) if transcripts_dir.exists() else 0
        await update.message.reply_text(
            f"Cheroki 상태:\n"
            f"  원본: {n_originals}개\n"
            f"  전사: {n_transcripts}개\n"
            f"  Whisper: {self.config['whisper']['model']} ({self.config['whisper'].get('mode', 'local')})"
        )

    # ── 전사 + 교정 플로우 ──────────────────────────────

    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
        """음성 파일 수신 → 전사 → AI 리뷰 시작."""
        if not update.effective_user or not update.message:
            return None
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("접근 권한이 없습니다.")
            return None

        message = update.message
        file_obj = message.audio or message.voice or message.document
        if not file_obj:
            return None

        if message.document and message.document.file_name:
            ext = Path(message.document.file_name).suffix.lower()
            if ext not in AUDIO_EXTENSIONS:
                await message.reply_text(f"지원하지 않는 형식입니다: {ext}")
                return None

        await message.reply_text("파일 수신 완료. 전사를 시작합니다...")

        try:
            result = await self._download_and_transcribe(file_obj, message, context)
        except Exception as e:
            logger.error("telegram_transcription_error", error=str(e))
            await message.reply_text(f"전사 중 오류가 발생했습니다: {e}")
            return None

        tr = result["result"]
        file_id = result["file_id"]

        # 전사 결과 전송
        text = _format_transcript(tr)
        duration_min = int(tr.duration // 60)
        duration_sec = int(tr.duration % 60)
        header = (
            f"전사 완료 (ID: {file_id})\n"
            f"세그먼트: {len(tr.segments)}개 | "
            f"길이: {duration_min}분 {duration_sec}초\n\n"
            f"--- 결과 ---"
        )
        if len(header) + len(text) + 2 > 3800:
            await message.reply_text(header)
            for chunk in _split_text(text, 3800):
                await message.reply_text(chunk)
        else:
            await message.reply_text(f"{header}\n{text}")

        # AI 교정 제안
        claude_key = self.config.get("claude_api", {}).get("api_key", "")
        if not claude_key:
            await message.reply_text(
                "교정 완료. (AI 교정을 사용하려면 config.yaml에 claude_api.api_key를 설정하세요)"
            )
            return None

        await message.reply_text("AI가 교정 제안을 준비 중...")

        suggestions = await self._get_ai_suggestions(tr, file_id)

        if not suggestions:
            await message.reply_text("AI 검토 결과 교정할 항목이 없습니다. 전사 품질 양호!")
            return None

        # 교정 세션 시작
        context.user_data["review_file_id"] = file_id
        context.user_data["review_result"] = tr
        context.user_data["suggestions"] = suggestions
        context.user_data["current_suggestion"] = 0
        context.user_data["corrections"] = []

        await message.reply_text(f"의심 구간 {len(suggestions)}개 발견. 교정을 시작합니다.\n/skip 으로 건너뛸 수 있습니다.\n")
        await self._send_suggestion(message, context)
        return REVIEWING

    async def _get_ai_suggestions(self, tr: Any, file_id: str) -> list[Any]:
        """AI 교정 제안을 받는다."""
        from cheroki.ai_reviewer import suggest_corrections_ai

        segments = []
        for i, seg in enumerate(tr.segments):
            segments.append({
                "index": i,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            })

        claude_key = self.config.get("claude_api", {}).get("api_key", "")
        loop = asyncio.get_event_loop()
        suggestions = await loop.run_in_executor(
            None,
            lambda: suggest_corrections_ai(segments, claude_key),
        )
        return suggestions

    async def _send_suggestion(self, message: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
        """현재 교정 제안을 보낸다."""
        suggestions = context.user_data.get("suggestions", [])
        idx = context.user_data.get("current_suggestion", 0)

        if idx >= len(suggestions):
            await self._finish_review(message, context)
            return

        s = suggestions[idx]
        keyboard = [
            [
                InlineKeyboardButton("✅ AI 제안 수락", callback_data="accept"),
                InlineKeyboardButton("⏭ 건너뛰기", callback_data="skip_one"),
            ],
            [
                InlineKeyboardButton("❌ 원본 유지", callback_data="keep"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.reply_text(
            f"[{idx + 1}/{len(suggestions)}] [{s.timestamp}]\n\n"
            f"현재: {s.original}\n"
            f"제안: {s.suggested}\n"
            f"사유: {s.reason}\n\n"
            f"직접 교정하려면 텍스트를 입력하세요.",
            reply_markup=reply_markup,
        )

    async def handle_review_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """교정 버튼 콜백."""
        query = update.callback_query
        if not query:
            return REVIEWING
        await query.answer()

        suggestions = context.user_data.get("suggestions", [])
        idx = context.user_data.get("current_suggestion", 0)

        if idx >= len(suggestions):
            if query.message:
                await self._finish_review(query.message, context)
            return ConversationHandler.END

        s = suggestions[idx]
        action = query.data

        if action == "accept":
            context.user_data["corrections"].append({
                "segment_index": s.segment_index,
                "corrected_text": s.suggested,
            })
            await query.edit_message_text(f"✅ [{s.timestamp}] {s.original} → {s.suggested}")
        elif action == "keep":
            await query.edit_message_text(f"⏸ [{s.timestamp}] 원본 유지: {s.original}")
        elif action == "skip_one":
            await query.edit_message_text(f"⏭ [{s.timestamp}] 건너뜀")

        context.user_data["current_suggestion"] = idx + 1
        if query.message:
            await self._send_suggestion(query.message, context)

        if context.user_data["current_suggestion"] >= len(suggestions):
            return ConversationHandler.END
        return REVIEWING

    async def handle_review_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """사용자가 직접 교정 텍스트를 입력."""
        if not update.message or not update.message.text:
            return REVIEWING

        suggestions = context.user_data.get("suggestions", [])
        idx = context.user_data.get("current_suggestion", 0)

        if idx >= len(suggestions):
            await self._finish_review(update.message, context)
            return ConversationHandler.END

        s = suggestions[idx]
        user_text = update.message.text.strip()

        context.user_data["corrections"].append({
            "segment_index": s.segment_index,
            "corrected_text": user_text,
        })
        await update.message.reply_text(f"✏️ [{s.timestamp}] {s.original} → {user_text}")

        context.user_data["current_suggestion"] = idx + 1
        await self._send_suggestion(update.message, context)

        if context.user_data["current_suggestion"] >= len(suggestions):
            return ConversationHandler.END
        return REVIEWING

    async def handle_skip(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """나머지 교정을 모두 건너뛴다."""
        if update.message:
            await update.message.reply_text("나머지 교정을 건너뜁니다.")
            await self._finish_review(update.message, context)
        return ConversationHandler.END

    async def _finish_review(self, message: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
        """교정 세션을 마무리하고 최종본을 생성한다."""
        corrections = context.user_data.get("corrections", [])
        file_id = context.user_data.get("review_file_id", "")
        tr = context.user_data.get("review_result")

        if not corrections:
            await message.reply_text("교정 완료. 변경 사항 없음.")
            self._clear_review_data(context)
            return

        # 교정 적용
        try:
            from cheroki.corrector import Correction, CorrectionSet, apply_corrections, save_corrections
            from cheroki.transcript_store import save_transcript
            from cheroki.corpus import save_corpus_pairs

            corr_objects = []
            for c in corrections:
                idx = c["segment_index"]
                original = tr.segments[idx].text.strip() if idx < len(tr.segments) else ""
                corr_objects.append(Correction(
                    segment_index=idx,
                    original_text=original,
                    corrected_text=c["corrected_text"],
                ))

            corrected = apply_corrections(tr, corr_objects)

            transcripts_dir = Path(self.config["paths"]["transcripts"])
            corrections_dir = Path(self.config["paths"]["corrections"])
            corpus_dir = Path(self.config["paths"]["corpus"])

            save_transcript(corrected, transcripts_dir, f"{file_id}_final")
            cs = CorrectionSet(file_id=file_id, corrections=corr_objects)
            save_corrections(cs, corrections_dir)
            save_corpus_pairs(file_id, corr_objects, corpus_dir, source_file=tr.source_file)

            await message.reply_text(
                f"교정 완료! {len(corrections)}개 수정됨.\n"
                f"최종본 저장: {file_id}_final\n\n"
                f"SRT/MD 내보내기: /export {file_id}"
            )
            logger.info("telegram_review_complete", file_id=file_id, corrections=len(corrections))

        except Exception as e:
            logger.error("telegram_review_error", error=str(e))
            await message.reply_text(f"교정 저장 중 오류: {e}")

        self._clear_review_data(context)

    def _clear_review_data(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """교정 세션 데이터 정리."""
        for key in ["review_file_id", "review_result", "suggestions", "current_suggestion", "corrections"]:
            context.user_data.pop(key, None)

    # ── 파일 다운로드 + 전사 ────────────────────────────

    async def _download_and_transcribe(
        self, file_obj: Any, message: Any, context: ContextTypes.DEFAULT_TYPE,
    ) -> dict[str, Any]:
        from cheroki.pipeline import run_pipeline

        originals_dir = Path(self.config["paths"]["originals"])
        originals_dir.mkdir(parents=True, exist_ok=True)

        tg_file = await context.bot.get_file(file_obj.file_id)
        if hasattr(file_obj, "file_name") and file_obj.file_name:
            filename = file_obj.file_name
        else:
            filename = f"voice_{file_obj.file_unique_id}.ogg"

        download_path = originals_dir / f"tg_{filename}"
        await tg_file.download_to_drive(str(download_path))
        logger.info("telegram_file_downloaded", path=str(download_path))

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: run_pipeline(download_path, config=self.config)
        )

        if download_path.exists():
            download_path.unlink()

        return result

    # ── 앱 구성 ─────────────────────────────────────────

    def build_application(self) -> Application:
        app = Application.builder().token(self.token).build()

        # 교정 대화 핸들러
        review_handler = ConversationHandler(
            entry_points=[
                MessageHandler(filters.AUDIO | filters.VOICE, self.handle_audio),
                MessageHandler(filters.Document.ALL, self.handle_audio),
            ],
            states={
                REVIEWING: [
                    CallbackQueryHandler(self.handle_review_callback),
                    CommandHandler("skip", self.handle_skip),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_review_text),
                ],
            },
            fallbacks=[
                CommandHandler("skip", self.handle_skip),
            ],
        )

        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(review_handler)

        return app

    def run(self) -> None:
        logger.info("telegram_bot_starting")
        app = self.build_application()
        app.run_polling(drop_pending_updates=True)


# ── 유틸리티 ────────────────────────────────────────────

def _format_timestamp(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _format_transcript(result: Any) -> str:
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
    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        idx = text.rfind("\n", 0, max_len)
        if idx == -1:
            idx = text.rfind(" ", 0, max_len)
        if idx == -1:
            idx = max_len
        chunks.append(text[:idx])
        text = text[idx:].lstrip()
    return chunks
