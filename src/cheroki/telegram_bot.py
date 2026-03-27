"""텔레그램 봇 모듈 — 음성 전사 + AI 일괄 교정 플로우."""

from __future__ import annotations

import asyncio
import re
import structlog
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from cheroki.config import get_config
from cheroki.storage import AUDIO_EXTENSIONS

logger = structlog.get_logger()

REVIEWING = 1


class CherokiBot:
    """텔레그램 봇 — 음성 전사 + 일괄 교정."""

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
            "Cheroki 전사 봇입니다.\n"
            "음성 파일을 보내면 전사 + AI 교정까지 진행합니다.\n\n"
            "/help — 도움말\n"
            "/status — 상태\n"
            "/done — 교정 종료"
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        await update.message.reply_text(
            "사용법:\n"
            "1. 음성 파일 전송 → 전사\n"
            "2. AI가 의심 구간을 한꺼번에 보여줍니다\n"
            "3. 번호와 교정을 보내세요\n"
            '   예: "1 예금이자는, 3 맞아, 5 XXX"\n'
            '   "확인" → AI 제안 전부 수락\n'
            "4. 남은 항목 계속 질문\n"
            "5. /done → 교정 종료 + 최종본 생성\n\n"
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
        """음성 파일 수신 → 전사 → AI 리뷰."""
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
            await message.reply_text(f"전사 중 오류: {e}")
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
            f"길이: {duration_min}분 {duration_sec}초\n\n--- 결과 ---"
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
            await message.reply_text("전사 완료. (AI 교정: config.yaml에 claude_api.api_key 설정 필요)")
            return None

        await message.reply_text("AI가 교정 제안을 준비 중...")

        suggestions = await self._get_ai_suggestions(tr, file_id)
        if not suggestions:
            await message.reply_text("AI 검토 결과 교정할 항목 없음. 전사 품질 양호!")
            return None

        # 교정 세션 저장
        context.user_data["file_id"] = file_id
        context.user_data["result"] = tr
        context.user_data["suggestions"] = {i + 1: s for i, s in enumerate(suggestions)}
        context.user_data["corrections"] = {}  # {seg_index: corrected_text}

        await self._send_suggestions(message, context)
        return REVIEWING

    async def _send_suggestions(self, message: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
        """미해결 의심 구간을 한꺼번에 보여준다."""
        suggestions = context.user_data.get("suggestions", {})
        corrections = context.user_data.get("corrections", {})

        # 아직 교정 안 된 항목
        pending = {k: s for k, s in suggestions.items() if s.segment_index not in corrections}

        if not pending:
            await message.reply_text("모든 항목이 교정되었습니다! /done 으로 최종본을 생성하세요.")
            return

        lines = [f"의심 구간 {len(pending)}개:\n"]
        for num, s in pending.items():
            if s.suggested:
                lines.append(f"  {num}. [{s.timestamp}] \"{s.original}\" → \"{s.suggested}\"")
                lines.append(f"      ({s.reason})")
            else:
                lines.append(f"  {num}. [{s.timestamp}] \"{s.original}\"")
                lines.append(f"      ({s.reason})")

        lines.append("")
        lines.append("교정 방법:")
        lines.append('  번호 교정내용 (예: "1 예금이자는")')
        lines.append('  "확인" → AI 제안 전부 수락')
        lines.append('  /done → 교정 종료 + 최종본 생성')

        text = "\n".join(lines)
        for chunk in _split_text(text, 3800):
            await message.reply_text(chunk)

    async def handle_review_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """사용자 교정 답변 처리."""
        if not update.message or not update.message.text:
            return REVIEWING

        text = update.message.text.strip()
        suggestions = context.user_data.get("suggestions", {})
        corrections = context.user_data.get("corrections", {})

        # "확인" → AI 제안 전부 수락
        if text in ("확인", "ㅇㅋ", "ok", "OK"):
            accepted = 0
            for num, s in suggestions.items():
                if s.segment_index not in corrections and s.suggested:
                    corrections[s.segment_index] = s.suggested
                    accepted += 1
            await update.message.reply_text(f"AI 제안 {accepted}개 일괄 수락.")
            await self._send_suggestions(update.message, context)
            if not any(s.segment_index not in corrections for s in suggestions.values()):
                await self._finish_review(update.message, context)
                return ConversationHandler.END
            return REVIEWING

        # 번호 + 교정 파싱: "1 예금이자는, 3 맞아" 또는 "1 예금이자는"
        parsed = _parse_corrections(text, suggestions)

        if parsed:
            for num, corrected in parsed.items():
                s = suggestions.get(num)
                if not s:
                    continue
                if corrected.lower() in ("맞아", "ㅇ", "수락", "ok"):
                    if s.suggested:
                        corrections[s.segment_index] = s.suggested
                        await update.message.reply_text(f"  {num}. ✅ {s.original} → {s.suggested}")
                    else:
                        await update.message.reply_text(f"  {num}. ⏸ AI 제안 없음 — 직접 입력해주세요")
                else:
                    corrections[s.segment_index] = corrected
                    await update.message.reply_text(f"  {num}. ✏️ {s.original} → {corrected}")

            context.user_data["corrections"] = corrections
            pending = {k: s for k, s in suggestions.items() if s.segment_index not in corrections}
            if not pending:
                await self._finish_review(update.message, context)
                return ConversationHandler.END
            await self._send_suggestions(update.message, context)
        else:
            await update.message.reply_text(
                '형식: "번호 교정내용" (예: "1 예금이자는")\n'
                '"확인" → AI 제안 전부 수락\n'
                "/done → 종료"
            )

        return REVIEWING

    async def handle_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """교정 종료."""
        if update.message:
            await self._finish_review(update.message, context)
        return ConversationHandler.END

    async def _finish_review(self, message: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
        """교정 반영 + 최종본 생성."""
        corrections = context.user_data.get("corrections", {})
        file_id = context.user_data.get("file_id", "")
        tr = context.user_data.get("result")

        if not corrections:
            await message.reply_text("변경 사항 없음. 교정 종료.")
            self._clear_data(context)
            return

        try:
            from cheroki.corrector import Correction, CorrectionSet, apply_corrections, save_corrections
            from cheroki.transcript_store import save_transcript
            from cheroki.corpus import save_corpus_pairs

            corr_objects = []
            for seg_idx, corrected_text in corrections.items():
                original = tr.segments[seg_idx].text.strip() if seg_idx < len(tr.segments) else ""
                corr_objects.append(Correction(
                    segment_index=seg_idx,
                    original_text=original,
                    corrected_text=corrected_text,
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
                f"교정 완료! {len(corrections)}개 수정.\n"
                f"최종본: {file_id}_final"
            )
            logger.info("review_complete", file_id=file_id, corrections=len(corrections))

        except Exception as e:
            logger.error("review_error", error=str(e))
            await message.reply_text(f"교정 저장 오류: {e}")

        self._clear_data(context)

    def _clear_data(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        for key in ["file_id", "result", "suggestions", "corrections"]:
            context.user_data.pop(key, None)

    # ── 전사 ────────────────────────────────────────────

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

    async def _get_ai_suggestions(self, tr: Any, file_id: str) -> list[Any]:
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
        return await loop.run_in_executor(
            None, lambda: suggest_corrections_ai(segments, claude_key),
        )

    # ── 앱 구성 ─────────────────────────────────────────

    def build_application(self) -> Application:
        app = Application.builder().token(self.token).build()

        review_handler = ConversationHandler(
            entry_points=[
                MessageHandler(filters.AUDIO | filters.VOICE, self.handle_audio),
                MessageHandler(filters.Document.ALL, self.handle_audio),
            ],
            states={
                REVIEWING: [
                    CommandHandler("done", self.handle_done),
                    CommandHandler("skip", self.handle_done),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_review_text),
                ],
            },
            fallbacks=[
                CommandHandler("done", self.handle_done),
                CommandHandler("skip", self.handle_done),
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


def _parse_corrections(text: str, suggestions: dict[int, Any]) -> dict[int, str]:
    """사용자 입력에서 번호+교정을 파싱.

    "1 예금이자는, 3 맞아" → {1: "예금이자는", 3: "맞아"}
    "1 예금이자는" → {1: "예금이자는"}
    """
    result: dict[int, str] = {}

    # 쉼표 또는 줄바꿈으로 분리
    parts = re.split(r"[,\n]", text)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        # "번호 텍스트" 패턴
        match = re.match(r"^(\d+)\s+(.+)$", part)
        if match:
            num = int(match.group(1))
            if num in suggestions:
                result[num] = match.group(2).strip()

    return result
