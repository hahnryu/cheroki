"""텔레그램 봇 모듈 — 음성 전사 + AI 일괄 교정 + 산출물 생성."""

from __future__ import annotations

import asyncio
import re
import structlog
from pathlib import Path
from typing import Any

from telegram import Update, InputFile
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

# 자연어 키워드
_SKIP_WORDS = {"무시", "패스", "skip", "넘어가", "넘겨", "건너뛰", "무시하면", "ㅌ"}
_ACCEPT_WORDS = {"맞아", "맞음", "ㅇ", "ㅇㅇ", "수락", "ok", "yes", "네", "응", "그래", "맞아요"}
_DEFER_WORDS = {"모르겠", "나중에", "문맥", "패스", "보류", "잘 모르", "다음에"}


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
            "음성 파일 → 전사 → AI 교정 → SRT/MD 생성\n\n"
            "/help — 도움말\n"
            "/status — 상태\n"
            "/done — 교정 종료\n"
            "/show — 최종본 보기"
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        await update.message.reply_text(
            "사용법:\n"
            "1. 음성 파일 전송 → 전사\n"
            "2. AI 의심 구간 한꺼번에 표시\n"
            "3. 교정 답변:\n"
            '   "1 예금이자는" — 직접 교정\n'
            '   "3 맞아" — AI 제안 수락\n'
            '   "2 무시" — 건너뛰기\n'
            '   "5 나중에" — 보류\n'
            '   "확인" — AI 제안 전부 수락\n'
            "4. /done — 교정 종료 + SRT/MD 생성\n"
            "5. /show — 최종본 보기\n\n"
            "지원: " + ", ".join(sorted(AUDIO_EXTENSIONS))
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

    async def cmd_show(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """최종본 또는 마지막 전사 결과를 보여준다."""
        if not update.message:
            return
        file_id = context.user_data.get("last_file_id", "")
        if not file_id:
            await update.message.reply_text("전사 결과가 없습니다. 음성 파일을 먼저 보내세요.")
            return

        from cheroki.transcript_store import load_transcript
        transcripts_dir = Path(self.config["paths"]["transcripts"])

        # 최종본 우선
        final_path = transcripts_dir / f"{file_id}_final.transcript.json"
        raw_path = transcripts_dir / f"{file_id}.transcript.json"
        path = final_path if final_path.exists() else raw_path

        if not path.exists():
            await update.message.reply_text(f"전사 결과를 찾을 수 없습니다: {file_id}")
            return

        tr = load_transcript(path)
        label = "최종본" if final_path.exists() else "원본"
        text = _format_transcript(tr)
        header = f"[{label}] {file_id}\n세그먼트: {len(tr.segments)}개\n\n"

        if len(header) + len(text) > 3800:
            await update.message.reply_text(header)
            for chunk in _split_text(text, 3800):
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(header + text)

    # ── 전사 + 교정 플로우 ──────────────────────────────

    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
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
            logger.error("transcription_error", error=str(e))
            await message.reply_text(f"전사 오류: {e}")
            return None

        tr = result["result"]
        file_id = result["file_id"]
        context.user_data["last_file_id"] = file_id

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

        # AI 교정
        claude_key = self.config.get("claude_api", {}).get("api_key", "")
        if not claude_key:
            await self._generate_exports(message, file_id, tr)
            return None

        await message.reply_text("AI가 교정 제안을 준비 중...")
        suggestions = await self._get_ai_suggestions(tr, file_id)

        if not suggestions:
            await message.reply_text("AI 검토 완료. 교정 필요 없음!")
            await self._generate_exports(message, file_id, tr)
            return None

        context.user_data["file_id"] = file_id
        context.user_data["result"] = tr
        context.user_data["suggestions"] = {i + 1: s for i, s in enumerate(suggestions)}
        context.user_data["corrections"] = {}
        context.user_data["deferred"] = set()  # 보류 항목

        await self._send_suggestions(message, context)
        return REVIEWING

    async def _send_suggestions(self, message: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
        suggestions = context.user_data.get("suggestions", {})
        corrections = context.user_data.get("corrections", {})
        deferred = context.user_data.get("deferred", set())

        pending = {k: s for k, s in suggestions.items()
                   if s.segment_index not in corrections and k not in deferred}

        if not pending:
            n_deferred = len(deferred)
            if n_deferred:
                await message.reply_text(
                    f"처리 완료. 보류 {n_deferred}개 남음.\n"
                    f"/done → 현재까지 교정 반영 + 산출물 생성"
                )
            else:
                await message.reply_text("모든 항목 교정 완료! /done 으로 최종본을 생성하세요.")
            return

        lines = [f"의심 구간 {len(pending)}개:\n"]
        for num, s in pending.items():
            if s.suggested:
                lines.append(f"  {num}. [{s.timestamp}] \"{s.original}\" → \"{s.suggested}\"")
            else:
                lines.append(f"  {num}. [{s.timestamp}] \"{s.original}\"")
            lines.append(f"      ({s.reason})")

        lines.append("")
        lines.append("답변 방법:")
        lines.append('  "번호 교정내용" / "번호 맞아" / "번호 무시"')
        lines.append('  "확인" → 전부 수락 / /done → 종료')

        text = "\n".join(lines)
        for chunk in _split_text(text, 3800):
            await message.reply_text(chunk)

    async def handle_review_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not update.message or not update.message.text:
            return REVIEWING

        text = update.message.text.strip()
        suggestions = context.user_data.get("suggestions", {})
        corrections = context.user_data.get("corrections", {})
        deferred = context.user_data.get("deferred", set())

        # "확인" → AI 제안 전부 수락
        if text.lower() in ("확인", "ㅇㅋ", "ok", "전부 수락"):
            accepted = 0
            for num, s in suggestions.items():
                if s.segment_index not in corrections and num not in deferred and s.suggested:
                    corrections[s.segment_index] = s.suggested
                    accepted += 1
            await update.message.reply_text(f"AI 제안 {accepted}개 일괄 수락.")
            pending = {k: s for k, s in suggestions.items()
                       if s.segment_index not in corrections and k not in deferred}
            if not pending:
                await self._finish_review(update.message, context)
                return ConversationHandler.END
            await self._send_suggestions(update.message, context)
            return REVIEWING

        # "보여줘" → 현재 전사 보기
        if text in ("보여줘", "보여주세요", "결과"):
            await self.cmd_show(update, context)
            return REVIEWING

        # 번호 + 교정 파싱
        parsed = _parse_corrections(text, suggestions)

        if parsed:
            for num, answer in parsed.items():
                s = suggestions.get(num)
                if not s:
                    continue

                action = _classify_answer(answer)

                if action == "skip":
                    corrections[s.segment_index] = s.original  # 원본 유지
                    await update.message.reply_text(f"  {num}. ⏭ 무시: {s.original}")
                elif action == "accept":
                    if s.suggested:
                        corrections[s.segment_index] = s.suggested
                        await update.message.reply_text(f"  {num}. ✅ {s.original} → {s.suggested}")
                    else:
                        await update.message.reply_text(f"  {num}. AI 제안 없음 — 직접 입력해주세요")
                elif action == "defer":
                    deferred.add(num)
                    await update.message.reply_text(f"  {num}. ⏸ 보류")
                else:
                    # 직접 교정 — "맞음." 같은 접미사 제거
                    clean = _clean_correction(answer)
                    corrections[s.segment_index] = clean
                    await update.message.reply_text(f"  {num}. ✏️ {s.original} → {clean}")

            context.user_data["corrections"] = corrections
            context.user_data["deferred"] = deferred

            pending = {k: s for k, s in suggestions.items()
                       if s.segment_index not in corrections and k not in deferred}
            if not pending:
                await self._finish_review(update.message, context)
                return ConversationHandler.END
            await self._send_suggestions(update.message, context)
        else:
            await update.message.reply_text(
                '형식: "번호 교정내용" (예: "1 예금이자는")\n'
                '"확인" / "보여줘" / /done'
            )

        return REVIEWING

    async def handle_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if update.message:
            await self._finish_review(update.message, context)
        return ConversationHandler.END

    async def _finish_review(self, message: Any, context: ContextTypes.DEFAULT_TYPE) -> None:
        corrections = context.user_data.get("corrections", {})
        file_id = context.user_data.get("file_id", "")
        tr = context.user_data.get("result")

        if not tr:
            await message.reply_text("전사 결과가 없습니다.")
            self._clear_data(context)
            return

        if corrections:
            try:
                from cheroki.corrector import Correction, CorrectionSet, apply_corrections, save_corrections
                from cheroki.transcript_store import save_transcript
                from cheroki.corpus import save_corpus_pairs

                corr_objects = []
                for seg_idx, corrected_text in corrections.items():
                    original = tr.segments[seg_idx].text.strip() if seg_idx < len(tr.segments) else ""
                    if original == corrected_text:
                        continue  # 원본 유지 (skip)
                    corr_objects.append(Correction(
                        segment_index=seg_idx,
                        original_text=original,
                        corrected_text=corrected_text,
                    ))

                if corr_objects:
                    corrected = apply_corrections(tr, corr_objects)
                    transcripts_dir = Path(self.config["paths"]["transcripts"])
                    corrections_dir = Path(self.config["paths"]["corrections"])
                    corpus_dir = Path(self.config["paths"]["corpus"])

                    save_transcript(corrected, transcripts_dir, f"{file_id}_final")
                    cs = CorrectionSet(file_id=file_id, corrections=corr_objects)
                    save_corrections(cs, corrections_dir)
                    save_corpus_pairs(file_id, corr_objects, corpus_dir, source_file=tr.source_file)
                    tr = corrected  # 산출물은 교정본으로

                    await message.reply_text(f"교정 완료! {len(corr_objects)}개 수정.")
                else:
                    await message.reply_text("실질 변경 없음.")
            except Exception as e:
                logger.error("review_error", error=str(e))
                await message.reply_text(f"교정 저장 오류: {e}")

        # SRT + MD 생성 + 전송
        await self._generate_exports(message, file_id, tr)
        self._clear_data(context)

    async def _generate_exports(self, message: Any, file_id: str, tr: Any) -> None:
        """SRT + MD 생성하고 텔레그램으로 파일 전송."""
        try:
            from cheroki.metadata import extract_metadata
            from cheroki.exporter import save_srt, save_markdown

            exports_dir = Path(self.config["paths"]["exports"])
            metadata = extract_metadata(file_id, source_file=tr.source_file, full_text=tr.full_text)

            srt_path = save_srt(tr, exports_dir, file_id)
            md_path = save_markdown(tr, exports_dir, file_id, metadata=metadata)

            # 파일 전송
            with open(srt_path, "rb") as f:
                await message.reply_document(
                    document=InputFile(f, filename=f"{file_id}.srt"),
                    caption="SRT 자막 파일",
                )
            with open(md_path, "rb") as f:
                await message.reply_document(
                    document=InputFile(f, filename=f"{file_id}.md"),
                    caption="Markdown 녹취록",
                )

            logger.info("exports_sent", file_id=file_id)
        except Exception as e:
            logger.error("export_error", error=str(e))
            await message.reply_text(f"산출물 생성 오류: {e}")

    def _clear_data(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        for key in ["file_id", "result", "suggestions", "corrections", "deferred"]:
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
                "index": i, "start": seg.start, "end": seg.end,
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
                    CommandHandler("show", self.cmd_show),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_review_text),
                ],
            },
            fallbacks=[
                CommandHandler("done", self.handle_done),
            ],
        )

        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("show", self.cmd_show))
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


def _classify_answer(answer: str) -> str:
    """답변을 분류: skip / accept / defer / correction."""
    lower = answer.lower().strip().rstrip(".")
    if any(w in lower for w in _SKIP_WORDS):
        return "skip"
    if any(w in lower for w in _DEFER_WORDS):
        return "defer"
    if lower in _ACCEPT_WORDS or any(w == lower for w in _ACCEPT_WORDS):
        return "accept"
    # "맞음"으로 끝나면 accept
    if lower.endswith("맞음") or lower.endswith("맞아") or lower.endswith("맞아요"):
        return "accept"
    return "correction"


def _clean_correction(text: str) -> str:
    """교정 텍스트에서 불필요한 접미사 제거."""
    # "competition 맞음" → "competition"
    # "인플레이션 맞아" → "인플레이션"
    for suffix in [" 맞음", " 맞아", " 맞아요", " 맞음.", " 맞아.", " ok", " ㅇ"]:
        if text.lower().endswith(suffix):
            return text[:len(text) - len(suffix)].strip()
    return text.strip()


def _parse_corrections(text: str, suggestions: dict[int, Any]) -> dict[int, str]:
    """사용자 입력에서 번호+교정을 파싱.

    지원 형식:
    - "1 예금이자는, 3 맞아"
    - "1 예금이자는\n3 맞아"
    - "1. 예금이자는"
    - "1 무시하면 됨."
    """
    result: dict[int, str] = {}
    parts = re.split(r"[,\n]", text)

    for part in parts:
        part = part.strip().rstrip(".")
        if not part:
            continue
        # "번호. 텍스트" 또는 "번호 텍스트"
        match = re.match(r"^(\d+)\.?\s+(.+)$", part)
        if match:
            num = int(match.group(1))
            if num in suggestions:
                result[num] = match.group(2).strip()

    return result
