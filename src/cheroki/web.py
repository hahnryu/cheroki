"""FastAPI 웹 서버 — 파일 업로드, 전사 상태 조회, 산출물 다운로드."""

from __future__ import annotations

import json
import structlog
from pathlib import Path
from typing import Any

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cheroki.config import get_config
from cheroki.storage import is_audio_file

logger = structlog.get_logger()

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app(config: dict[str, Any] | None = None) -> FastAPI:
    """FastAPI 앱을 생성한다."""
    app = FastAPI(title="Cheroki", description="음성 전사 파이프라인")
    app.state.config = config or get_config()

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    # ── 페이지 ──────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """메인 페이지."""
        cfg = app.state.config
        originals_dir = Path(cfg["paths"]["originals"])
        transcripts_dir = Path(cfg["paths"]["transcripts"])
        exports_dir = Path(cfg["paths"]["exports"])

        # 파일 목록 수집
        files = _list_files(originals_dir, transcripts_dir, exports_dir)

        return templates.TemplateResponse(
            request,
            "index.html",
            {"files": files, "config": cfg},
        )

    # ── API ─────────────────────────────────────────────

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...)) -> JSONResponse:
        """음성 파일 업로드 → 전사 실행."""
        if not file.filename:
            raise HTTPException(400, "파일 이름이 없습니다")

        if not is_audio_file(Path(file.filename)):
            raise HTTPException(400, f"지원하지 않는 형식: {Path(file.filename).suffix}")

        cfg = app.state.config
        originals_dir = Path(cfg["paths"]["originals"])
        originals_dir.mkdir(parents=True, exist_ok=True)

        # 임시 저장
        temp_path = originals_dir / f"web_{file.filename}"
        content = await file.read()
        temp_path.write_bytes(content)

        try:
            from cheroki.pipeline import run_pipeline
            result = run_pipeline(temp_path, config=cfg)
            # 임시 파일 삭제 (pipeline이 originals/에 복사함)
            if temp_path.exists():
                temp_path.unlink()

            return JSONResponse({
                "status": "ok",
                "file_id": result["file_id"],
                "segments": len(result["result"].segments),
                "duration": result["result"].duration,
                "text_preview": result["result"].full_text[:300],
            })
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            logger.error("web_upload_error", error=str(e))
            raise HTTPException(500, f"전사 실패: {e}")

    @app.get("/api/files")
    async def list_files() -> JSONResponse:
        """전사 파일 목록."""
        cfg = app.state.config
        files = _list_files(
            Path(cfg["paths"]["originals"]),
            Path(cfg["paths"]["transcripts"]),
            Path(cfg["paths"]["exports"]),
        )
        return JSONResponse({"files": files})

    @app.get("/api/transcript/{file_id}")
    async def get_transcript(file_id: str) -> JSONResponse:
        """전사 결과 조회."""
        cfg = app.state.config
        transcripts_dir = Path(cfg["paths"]["transcripts"])

        # 최종본 우선
        for suffix in ["_final.transcript.json", ".transcript.json"]:
            path = transcripts_dir / f"{file_id}{suffix}"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return JSONResponse(data)

        raise HTTPException(404, f"전사 결과 없음: {file_id}")

    @app.post("/api/export/{file_id}")
    async def export_file(file_id: str) -> JSONResponse:
        """SRT + MD 산출물 생성."""
        cfg = app.state.config
        transcripts_dir = Path(cfg["paths"]["transcripts"])
        exports_dir = Path(cfg["paths"]["exports"])

        # 전사 결과 로드
        from cheroki.transcript_store import load_transcript
        from cheroki.metadata import extract_metadata
        from cheroki.exporter import save_srt, save_markdown

        final_path = transcripts_dir / f"{file_id}_final.transcript.json"
        original_path = transcripts_dir / f"{file_id}.transcript.json"
        transcript_path = final_path if final_path.exists() else original_path

        if not transcript_path.exists():
            raise HTTPException(404, f"전사 결과 없음: {file_id}")

        result = load_transcript(transcript_path)
        metadata = extract_metadata(file_id, source_file=result.source_file, full_text=result.full_text)

        srt_path = save_srt(result, exports_dir, file_id)
        md_path = save_markdown(result, exports_dir, file_id, metadata=metadata)

        return JSONResponse({
            "status": "ok",
            "srt": str(srt_path),
            "md": str(md_path),
        })

    @app.get("/api/download/{file_id}/{fmt}")
    async def download(file_id: str, fmt: str) -> FileResponse:
        """산출물 다운로드 (srt 또는 md)."""
        cfg = app.state.config
        exports_dir = Path(cfg["paths"]["exports"])

        if fmt not in ("srt", "md"):
            raise HTTPException(400, f"지원하지 않는 형식: {fmt}")

        path = exports_dir / f"{file_id}.{fmt}"
        if not path.exists():
            raise HTTPException(404, f"파일 없음: {file_id}.{fmt}")

        return FileResponse(
            path=str(path),
            filename=f"{file_id}.{fmt}",
            media_type="application/octet-stream",
        )

    @app.get("/api/status")
    async def status() -> JSONResponse:
        """서버 상태."""
        cfg = app.state.config
        return JSONResponse({
            "status": "ok",
            "whisper_model": cfg["whisper"]["model"],
            "language": cfg["whisper"]["language"],
        })

    return app


def _list_files(
    originals_dir: Path,
    transcripts_dir: Path,
    exports_dir: Path,
) -> list[dict[str, Any]]:
    """전사 파일 목록을 수집한다."""
    files: list[dict[str, Any]] = []

    if not originals_dir.exists():
        return files

    for meta_path in sorted(originals_dir.glob("*.meta.json"), reverse=True):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        file_id = meta["file_id"]

        has_transcript = (transcripts_dir / f"{file_id}.transcript.json").exists()
        has_final = (transcripts_dir / f"{file_id}_final.transcript.json").exists()
        has_srt = (exports_dir / f"{file_id}.srt").exists()
        has_md = (exports_dir / f"{file_id}.md").exists()

        files.append({
            "file_id": file_id,
            "original_name": meta.get("original_name", ""),
            "stored_at": meta.get("stored_at", ""),
            "size_bytes": meta.get("size_bytes", 0),
            "has_transcript": has_transcript,
            "has_final": has_final,
            "has_exports": has_srt or has_md,
        })

    return files
