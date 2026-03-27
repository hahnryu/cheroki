"""텔레그램 봇 — 전사 + 교정 + 산출물 + vault + 학습 통합."""

from __future__ import annotations

import asyncio
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

CORRECTING = 1


class CherokiBot:
    """텔레그램 봇."""

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

    # ── /start ──────────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("접근 권한이 없습니다.")
            return
        await update.message.reply_text(
            "Cheroki 전사 봇\n\n"
            "음성 파일을 보내면 자동으로:\n"
            "전사 → SRT/MD 생성 → vault 싱크\n\n"
            "/help 로 전체 명령어 확인"
        )

    # ── /help ───────────────────────────────────────────

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        await update.message.reply_text(
            "📖 Cheroki 매뉴얼\n\n"
            "━━ 전사 ━━\n"
            "음성 파일 전송 → 자동 전사 + SRT/MD + vault 싱크\n"
            f"지원: {', '.join(sorted(AUDIO_EXTENSIONS))}\n\n"
            "━━ 교정 ━━\n"
            "/correct — 교정 시작\n"
            "  → AI가 의심 구간 질문\n"
            "  → 자유롭게 답변\n"
            "  → AI가 해석해서 교정 반영\n"
            "  → 미해결 항목 재질문\n"
            "/done — 교정 종료\n\n"
            "━━ 조회 ━━\n"
            "/show — 최근 전사 결과\n"
            "/list — 전사 파일 목록\n"
            "/status — 시스템 상태\n\n"
            "━━ 산출물 ━━\n"
            "/export — SRT + MD 재생성\n"
            "/vault — Hahnness vault 싱크\n\n"
            "━━ 학습 ━━\n"
            "/learn — 교정 패턴 학습 + 사전 업데이트\n"
            "/dataset — 코퍼스 내보내기 (JSONL)\n"
        )

    # ── /status ─────────────────────────────────────────

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        originals = Path(self.config["paths"]["originals"])
        transcripts = Path(self.config["paths"]["transcripts"])
        corpus = Path(self.config["paths"]["corpus"])
        n_orig = len(list(originals.glob("*.meta.json"))) if originals.exists() else 0
        n_trans = len(list(transcripts.glob("*.transcript.json"))) if transcripts.exists() else 0
        n_corpus = len(list(corpus.glob("*.corpus.json"))) if corpus.exists() else 0
        mode = self.config["whisper"].get("mode", "local")
        model = self.config["whisper"]["model"]
        has_claude = bool(self.config.get("claude_api", {}).get("api_key", ""))
        await update.message.reply_text(
            f"Cheroki 상태\n"
            f"  Whisper: {model} ({mode})\n"
            f"  AI 교정: {'활성' if has_claude else '비활성'}\n"
            f"  원본: {n_orig}개\n"
            f"  전사: {n_trans}개\n"
            f"  코퍼스: {n_corpus}개"
        )

    # ── /list ───────────────────────────────────────────

    async def cmd_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        originals = Path(self.config["paths"]["originals"])
        if not originals.exists():
            await update.message.reply_text("전사 파일 없음.")
            return
        import json
        metas = sorted(originals.glob("*.meta.json"), reverse=True)
        if not metas:
            await update.message.reply_text("전사 파일 없음.")
            return
        lines = ["최근 전사 파일:\n"]
        for m in metas[:15]:
            data = json.loads(m.read_text(encoding="utf-8"))
            fid = data["file_id"]
            name = data.get("original_name", "")
            lines.append(f"  {name}\n  ID: {fid}\n")
        await update.message.reply_text("\n".join(lines))

    # ── /show ───────────────────────────────────────────

    async def cmd_show(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        file_id = context.user_data.get("last_file_id", "")
        if not file_id:
            await update.message.reply_text("전사 결과 없음. 음성 파일을 먼저 보내세요.")
            return
        from cheroki.transcript_store import load_transcript
        transcripts_dir = Path(self.config["paths"]["transcripts"])
        final_path = transcripts_dir / f"{file_id}_final.transcript.json"
        raw_path = transcripts_dir / f"{file_id}.transcript.json"
        path = final_path if final_path.exists() else raw_path
        if not path.exists():
            await update.message.reply_text(f"파일 없음: {file_id}")
            return
        tr = load_transcript(path)
        label = "최종본" if final_path.exists() else "원본"
        text = _format_transcript(tr)
        header = f"[{label}] {file_id}\n"
        for chunk in _split_text(header + text, 3800):
            await update.message.reply_text(chunk)

    # ── /export ─────────────────────────────────────────

    async def cmd_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        file_id = context.user_data.get("last_file_id", "")
        if not file_id:
            await update.message.reply_text("전사 결과 없음.")
            return
        tr = self._load_best_transcript(file_id)
        if not tr:
            await update.message.reply_text(f"파일 없음: {file_id}")
            return
        await self._generate_exports(update.message, file_id, tr)

    # ── /vault ──────────────────────────────────────────

    async def cmd_vault(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        file_id = context.user_data.get("last_file_id", "")
        if not file_id:
            await update.message.reply_text("전사 결과 없음.")
            return
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._sync_vault(file_id)
        )
        await update.message.reply_text(result)

    # ── /learn ──────────────────────────────────────────

    async def cmd_learn(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        await update.message.reply_text("패턴 학습 중...")
        result = await asyncio.get_event_loop().run_in_executor(
            None, self._run_learn
        )
        await update.message.reply_text(result)

    # ── /dataset ────────────────────────────────────────

    async def cmd_dataset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        from cheroki.dataset import export_jsonl
        corpus_dir = Path(self.config["paths"]["corpus"])
        exports_dir = Path(self.config["paths"]["exports"])
        out = export_jsonl(corpus_dir, exports_dir / "dataset.jsonl")
        if out.exists() and out.stat().st_size > 0:
            with open(out, "rb") as f:
                await update.message.reply_document(
                    document=InputFile(f, filename="dataset.jsonl"),
                    caption="코퍼스 데이터셋 (JSONL)",
                )
        else:
            await update.message.reply_text("코퍼스가 비어있습니다. 교정을 먼저 진행하세요.")

    # ── 음성 파일 수신 → 자동 전사 파이프라인 ───────────

    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("접근 권한이 없습니다.")
            return

        message = update.message
        file_obj = message.audio or message.voice or message.document
        if not file_obj:
            return

        if message.document and message.document.file_name:
            ext = Path(message.document.file_name).suffix.lower()
            if ext not in AUDIO_EXTENSIONS:
                await message.reply_text(f"지원하지 않는 형식: {ext}")
                return

        await message.reply_text("파일 수신. 전사를 시작합니다...")

        try:
            result = await self._download_and_transcribe(file_obj, message, context)
        except Exception as e:
            logger.error("transcription_error", error=str(e))
            await message.reply_text(f"전사 오류: {e}")
            return

        tr = result["result"]
        file_id = result["file_id"]
        context.user_data["last_file_id"] = file_id

        # 1. 전사 결과 전송
        text = _format_transcript(tr)
        duration_min = int(tr.duration // 60)
        duration_sec = int(tr.duration % 60)
        header = (
            f"전사 완료 ({file_id})\n"
            f"{len(tr.segments)}개 세그먼트 | {duration_min}분 {duration_sec}초\n\n"
        )
        for chunk in _split_text(header + text, 3800):
            await message.reply_text(chunk)

        # 2. SRT + MD 자동 생성 + 전송
        await self._generate_exports(message, file_id, tr)

        # 3. Vault 싱크
        vault_result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._sync_vault(file_id)
        )
        if "완료" in vault_result:
            await message.reply_text(vault_result)

        # 4. 안내
        await message.reply_text("교정하려면 /correct 를 보내세요.")

    # ── /correct — 대화형 교정 ──────────────────────────

    async def cmd_correct(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
        if not update.message:
            return None
        file_id = context.user_data.get("last_file_id", "")
        if not file_id:
            await update.message.reply_text("전사 결과 없음. 음성 파일을 먼저 보내세요.")
            return None

        tr = self._load_best_transcript(file_id)
        if not tr:
            await update.message.reply_text(f"파일 없음: {file_id}")
            return None

        claude_key = self.config.get("claude_api", {}).get("api_key", "")
        if not claude_key:
            await update.message.reply_text("AI 교정 비활성. config.yaml에 claude_api.api_key를 설정하세요.")
            return None

        context.user_data["correct_file_id"] = file_id
        context.user_data["correct_result"] = tr
        context.user_data["correct_history"] = []  # 대화 이력

        await update.message.reply_text("AI가 전사 결과를 분석 중...")

        # AI에게 첫 질문 요청
        questions = await self._ask_ai_questions(tr, context)
        if not questions:
            await update.message.reply_text("AI 분석 완료. 교정할 항목 없음!")
            return None

        await update.message.reply_text(questions)
        return CORRECTING

    async def handle_correct_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """사용자 답변 → AI가 해석 + 교정 반영 + 추가 질문."""
        if not update.message or not update.message.text:
            return CORRECTING

        user_text = update.message.text.strip()
        tr = context.user_data.get("correct_result")
        history = context.user_data.get("correct_history", [])

        if not tr:
            await update.message.reply_text("교정 세션이 없습니다. /correct 로 시작하세요.")
            return ConversationHandler.END

        # 대화 이력에 사용자 답변 추가
        history.append({"role": "user", "content": user_text})

        await update.message.reply_text("AI가 답변을 처리 중...")

        # AI에게 답변 해석 + 교정 적용 + 추가 질문 요청
        ai_response = await self._process_correction_reply(tr, history, context)

        if ai_response.get("done"):
            # 교정 적용
            corrections = ai_response.get("corrections", [])
            if corrections:
                await self._apply_corrections(update.message, context, corrections)
            else:
                await update.message.reply_text("교정 완료. 변경 없음.")
            return ConversationHandler.END

        # 추가 질문
        if ai_response.get("message"):
            history.append({"role": "assistant", "content": ai_response["message"]})
            context.user_data["correct_history"] = history
            await update.message.reply_text(ai_response["message"])

        return CORRECTING

    async def cmd_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """교정 강제 종료."""
        if not update.message:
            return ConversationHandler.END

        # 현재까지 AI가 파악한 교정 적용
        history = context.user_data.get("correct_history", [])
        tr = context.user_data.get("correct_result")
        if tr and history:
            ai_response = await self._finalize_corrections(tr, history, context)
            corrections = ai_response.get("corrections", [])
            if corrections:
                await self._apply_corrections(update.message, context, corrections)
            else:
                await update.message.reply_text("교정 종료. 변경 없음.")
        else:
            await update.message.reply_text("교정 종료.")

        self._clear_correct_data(context)
        return ConversationHandler.END

    # ── AI 대화 ─────────────────────────────────────────

    async def _ask_ai_questions(self, tr: Any, context: ContextTypes.DEFAULT_TYPE) -> str:
        """AI에게 전사 결과를 보내고 질문을 받는다."""
        from cheroki.ai_reviewer import suggest_corrections_ai

        segments = [{"index": i, "start": s.start, "end": s.end, "text": s.text.strip()}
                    for i, s in enumerate(tr.segments)]
        claude_key = self.config.get("claude_api", {}).get("api_key", "")

        suggestions = await asyncio.get_event_loop().run_in_executor(
            None, lambda: suggest_corrections_ai(segments, claude_key),
        )

        if not suggestions:
            return ""

        # 질문 포맷
        lines = ["다음 부분을 확인해주세요:\n"]
        for i, s in enumerate(suggestions, 1):
            if s.suggested:
                lines.append(f"{i}. [{s.timestamp}] \"{s.original}\" → \"{s.suggested}\"?")
            else:
                lines.append(f"{i}. [{s.timestamp}] \"{s.original}\" — {s.reason}")

        lines.append("\n자유롭게 답변하세요. /done 으로 종료.")

        msg = "\n".join(lines)
        context.user_data["correct_suggestions"] = suggestions
        context.user_data["correct_history"] = [{"role": "assistant", "content": msg}]
        return msg

    async def _process_correction_reply(
        self, tr: Any, history: list[dict], context: ContextTypes.DEFAULT_TYPE,
    ) -> dict[str, Any]:
        """AI에게 사용자 답변을 보내고 교정 해석 + 추가 질문을 받는다."""
        import json
        import urllib.request

        claude_key = self.config.get("claude_api", {}).get("api_key", "")

        # 전사 텍스트 구성
        seg_text = "\n".join(
            f"[{i}] [{_fmt_ts(s.start)}] {s.text.strip()}"
            for i, s in enumerate(tr.segments)
        )

        system_prompt = (
            "너는 한국어 음성 전사 교정 어시스턴트다.\n"
            "전사 결과와 대화 이력이 주어진다.\n"
            "사용자의 답변을 해석하여:\n"
            "1. 확인된 교정 사항을 정리하고\n"
            "2. 아직 불명확한 부분이 있으면 추가 질문하고\n"
            "3. 모두 해결되면 최종 교정 목록을 JSON으로 반환해라\n\n"
            "응답 형식:\n"
            "- 추가 질문이 있으면: 자연스러운 한국어로 질문. 마지막 줄에 [CONTINUE]\n"
            "- 모두 해결되면: 마지막 줄에 [CORRECTIONS]와 JSON 배열:\n"
            '  [CORRECTIONS][{"segment_index": 0, "corrected_text": "교정된 텍스트"}, ...]\n\n'
            f"전사 결과:\n{seg_text}"
        )

        messages = [{"role": "user", "content": system_prompt}] + history

        payload = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2000,
            "system": "음성 전사 교정 어시스턴트. 한국어로 대화.",
            "messages": messages,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key": claude_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            resp_data = await asyncio.get_event_loop().run_in_executor(
                None, lambda: json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
            )
        except Exception as e:
            logger.error("claude_error", error=str(e))
            return {"message": f"AI 오류: {e}. /done 으로 종료하세요.", "done": False}

        text_content = ""
        for block in resp_data.get("content", []):
            if block.get("type") == "text":
                text_content += block["text"]

        # 파싱
        if "[CORRECTIONS]" in text_content:
            parts = text_content.split("[CORRECTIONS]")
            message = parts[0].strip()
            json_str = parts[1].strip()
            try:
                corrections = json.loads(json_str)
            except json.JSONDecodeError:
                # JSON 부분만 추출
                start = json_str.find("[")
                end = json_str.rfind("]") + 1
                try:
                    corrections = json.loads(json_str[start:end]) if start >= 0 else []
                except json.JSONDecodeError:
                    corrections = []
            return {"done": True, "corrections": corrections, "message": message}

        # 아직 계속
        message = text_content.replace("[CONTINUE]", "").strip()
        return {"done": False, "message": message}

    async def _finalize_corrections(
        self, tr: Any, history: list[dict], context: ContextTypes.DEFAULT_TYPE,
    ) -> dict[str, Any]:
        """대화 종료 시 현재까지 파악된 교정 사항을 정리."""
        history_copy = history + [
            {"role": "user", "content": "교정을 종료합니다. 지금까지 확인된 교정 사항을 [CORRECTIONS] 형식으로 정리해주세요."}
        ]
        return await self._process_correction_reply(tr, history_copy, context)

    async def _apply_corrections(
        self, message: Any, context: ContextTypes.DEFAULT_TYPE, corrections: list[dict],
    ) -> None:
        """교정 적용 → 최종본 → SRT/MD → vault → 코퍼스 → 학습."""
        file_id = context.user_data.get("correct_file_id", "")
        tr = context.user_data.get("correct_result")
        if not tr or not file_id:
            return

        try:
            from cheroki.corrector import Correction, CorrectionSet, apply_corrections, save_corrections
            from cheroki.transcript_store import save_transcript
            from cheroki.corpus import save_corpus_pairs

            corr_objects = []
            for c in corrections:
                idx = c.get("segment_index", -1)
                if 0 <= idx < len(tr.segments):
                    original = tr.segments[idx].text.strip()
                    corrected = c.get("corrected_text", "")
                    if original != corrected and corrected:
                        corr_objects.append(Correction(
                            segment_index=idx,
                            original_text=original,
                            corrected_text=corrected,
                        ))

            if not corr_objects:
                await message.reply_text("실질 변경 없음.")
                self._clear_correct_data(context)
                return

            corrected_tr = apply_corrections(tr, corr_objects)
            transcripts_dir = Path(self.config["paths"]["transcripts"])
            corrections_dir = Path(self.config["paths"]["corrections"])
            corpus_dir = Path(self.config["paths"]["corpus"])

            # 1. 최종본 저장
            save_transcript(corrected_tr, transcripts_dir, f"{file_id}_final")

            # 2. 교정 이력
            cs = CorrectionSet(file_id=file_id, corrections=corr_objects)
            save_corrections(cs, corrections_dir)

            # 3. 코퍼스
            save_corpus_pairs(file_id, corr_objects, corpus_dir, source_file=tr.source_file)

            # 교정 내역 보여주기
            lines = [f"교정 완료! {len(corr_objects)}개 수정:\n"]
            for c in corr_objects:
                lines.append(f"  [{_fmt_ts(tr.segments[c.segment_index].start)}] {c.original_text} → {c.corrected_text}")
            await message.reply_text("\n".join(lines))

            # 4. SRT + MD 재생성 + 전송
            await self._generate_exports(message, file_id, corrected_tr)

            # 5. Vault 재싱크
            vault_result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._sync_vault(file_id)
            )
            if "완료" in vault_result:
                await message.reply_text(vault_result)

            # 6. 패턴 학습
            learn_result = await asyncio.get_event_loop().run_in_executor(
                None, self._run_learn
            )
            if "추가" in learn_result or "학습" in learn_result:
                await message.reply_text(learn_result)

            logger.info("correction_complete", file_id=file_id, count=len(corr_objects))

        except Exception as e:
            logger.error("correction_error", error=str(e))
            await message.reply_text(f"교정 오류: {e}")

        self._clear_correct_data(context)

    # ── 공통 기능 ───────────────────────────────────────

    def _load_best_transcript(self, file_id: str) -> Any:
        from cheroki.transcript_store import load_transcript
        transcripts_dir = Path(self.config["paths"]["transcripts"])
        for suffix in [f"{file_id}_final.transcript.json", f"{file_id}.transcript.json"]:
            path = transcripts_dir / suffix
            if path.exists():
                return load_transcript(path)
        return None

    async def _generate_exports(self, message: Any, file_id: str, tr: Any) -> None:
        try:
            from cheroki.metadata import extract_metadata
            from cheroki.exporter import save_srt, save_markdown

            exports_dir = Path(self.config["paths"]["exports"])
            metadata = extract_metadata(file_id, source_file=tr.source_file, full_text=tr.full_text)

            srt_path = save_srt(tr, exports_dir, file_id)
            md_path = save_markdown(tr, exports_dir, file_id, metadata=metadata)

            with open(srt_path, "rb") as f:
                await message.reply_document(InputFile(f, filename=f"{file_id}.srt"), caption="SRT")
            with open(md_path, "rb") as f:
                await message.reply_document(InputFile(f, filename=f"{file_id}.md"), caption="MD")
        except Exception as e:
            logger.error("export_error", error=str(e))
            await message.reply_text(f"산출물 오류: {e}")

    def _sync_vault(self, file_id: str) -> str:
        from cheroki.learner import route_to_vault
        exports_dir = Path(self.config["paths"]["exports"])
        md_path = exports_dir / f"{file_id}.md"
        if not md_path.exists():
            return "vault: MD 파일 없음"
        dest = route_to_vault(md_path, self.config)
        if dest:
            return f"vault 싱크 완료: {dest.name}"
        return "vault 미설정 또는 경로 없음"

    def _run_learn(self) -> str:
        from cheroki.dictionary import Dictionary
        from cheroki.learner import auto_update_dictionary, learn_correction_patterns, save_patterns

        corpus_dir = Path(self.config["paths"]["corpus"])
        dictionary = Dictionary.from_config(self.config)

        added = auto_update_dictionary(corpus_dir, dictionary, min_frequency=2)
        if added:
            dict_dir = Path(__file__).resolve().parents[1] / "dictionary"
            dict_dir.mkdir(parents=True, exist_ok=True)
            dictionary.save_file(dict_dir / "auto_learned.yaml")

        patterns = learn_correction_patterns(corpus_dir)
        if patterns:
            patterns_path = Path(self.config["paths"]["corrections"]) / "patterns.json"
            save_patterns(patterns, patterns_path)

        parts = []
        if added:
            parts.append(f"사전에 {len(added)}개 추가: {', '.join(added[:5])}")
        if patterns:
            parts.append(f"패턴 {len(patterns)}개 학습")
        return "\n".join(parts) if parts else "새로운 학습 항목 없음"

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

    def _clear_correct_data(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        for key in ["correct_file_id", "correct_result", "correct_history", "correct_suggestions"]:
            context.user_data.pop(key, None)

    # ── 앱 구성 ─────────────────────────────────────────

    def build_application(self) -> Application:
        app = Application.builder().token(self.token).build()

        correct_handler = ConversationHandler(
            entry_points=[CommandHandler("correct", self.cmd_correct)],
            states={
                CORRECTING: [
                    CommandHandler("done", self.cmd_done),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_correct_reply),
                ],
            },
            fallbacks=[CommandHandler("done", self.cmd_done)],
        )

        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("list", self.cmd_list))
        app.add_handler(CommandHandler("show", self.cmd_show))
        app.add_handler(CommandHandler("export", self.cmd_export))
        app.add_handler(CommandHandler("vault", self.cmd_vault))
        app.add_handler(CommandHandler("learn", self.cmd_learn))
        app.add_handler(CommandHandler("dataset", self.cmd_dataset))
        app.add_handler(correct_handler)
        app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, self.handle_audio))
        app.add_handler(MessageHandler(filters.Document.ALL, self.handle_audio))

        return app

    def run(self) -> None:
        logger.info("telegram_bot_starting")
        app = self.build_application()
        app.run_polling(drop_pending_updates=True)


# ── 유틸리티 ────────────────────────────────────────────

def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _format_transcript(result: Any) -> str:
    lines: list[str] = []
    for seg in result.segments:
        ts = _fmt_ts(seg.start)
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
