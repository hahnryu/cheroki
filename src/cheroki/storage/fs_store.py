from __future__ import annotations

import json
import logging
from pathlib import Path

from cheroki.core.result import TranscriptionResult

logger = logging.getLogger(__name__)


class FileStore:
    """파일시스템 기반 원본/산출물 저장."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.uploads_dir = self.data_dir / "uploads"
        self.exports_dir = self.data_dir / "exports"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 경로 계산 ----------

    def upload_path(self, record_id: str, suffix: str) -> Path:
        """원본 오디오 저장 경로. suffix는 확장자(`.m4a`)."""
        if suffix and not suffix.startswith("."):
            suffix = f".{suffix}"
        return self.uploads_dir / f"{record_id}{suffix}"

    def srt_path(self, record_id: str) -> Path:
        return self.exports_dir / f"{record_id}.srt"

    def md_path(self, record_id: str) -> Path:
        return self.exports_dir / f"{record_id}.md"

    def txt_path(self, record_id: str) -> Path:
        return self.exports_dir / f"{record_id}.txt"

    def raw_json_path(self, record_id: str) -> Path:
        return self.exports_dir / f"{record_id}.raw.json"

    # ---------- 산출물 쓰기 ----------

    def write_exports(
        self,
        record_id: str,
        result: TranscriptionResult,
        *,
        title: str | None = None,
    ) -> dict[str, Path]:
        srt = self.srt_path(record_id)
        md = self.md_path(record_id)
        txt = self.txt_path(record_id)
        raw = self.raw_json_path(record_id)

        srt.write_text(result.to_srt(), encoding="utf-8")
        md.write_text(result.to_markdown(title=title), encoding="utf-8")
        txt.write_text(result.to_txt(), encoding="utf-8")
        raw.write_text(
            json.dumps(result.raw_response, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info("산출물 기록: %s (4개 파일)", record_id)
        return {"srt": srt, "md": md, "txt": txt, "raw": raw}
