from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from cheroki.core.result import TranscriptionResult
from cheroki.naming import session_folder_name

logger = logging.getLogger(__name__)


class FileStore:
    """파일시스템 기반 원본/산출물 저장.

    레이아웃:
        DATA_DIR/YYMMDD/<slug>_raw.<audio_ext>   원본 오디오
        DATA_DIR/YYMMDD/<slug>_raw.srt           자막
        DATA_DIR/YYMMDD/<slug>_raw.md            Markdown 전사본 (frontmatter 포함)
        DATA_DIR/YYMMDD/<slug>_raw.txt           플레인 텍스트
        DATA_DIR/YYMMDD/<slug>_raw.json          Deepgram 원본 응답

    `_raw` 접미어는 1차 채록 산출물임을 표시한다. 이후 교정·이름지정 모듈이 만드는
    수정본은 다른 접미어(`_edited`, `_named` 등)를 쓴다.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def session_dir(self, recording_date: date) -> Path:
        d = self.data_dir / session_folder_name(recording_date)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---------- 경로 계산 ----------

    def audio_path(self, recording_date: date, slug: str, suffix: str) -> Path:
        if suffix and not suffix.startswith("."):
            suffix = f".{suffix}"
        return self.session_dir(recording_date) / f"{slug}_raw{suffix}"

    def srt_path(self, recording_date: date, slug: str) -> Path:
        return self.session_dir(recording_date) / f"{slug}_raw.srt"

    def md_path(self, recording_date: date, slug: str) -> Path:
        return self.session_dir(recording_date) / f"{slug}_raw.md"

    def txt_path(self, recording_date: date, slug: str) -> Path:
        return self.session_dir(recording_date) / f"{slug}_raw.txt"

    def raw_json_path(self, recording_date: date, slug: str) -> Path:
        return self.session_dir(recording_date) / f"{slug}_raw.json"

    # ---------- 산출물 쓰기 ----------

    def write_exports(
        self,
        recording_date: date,
        slug: str,
        result: TranscriptionResult,
        *,
        frontmatter_extra: dict | None = None,
    ) -> dict[str, Path]:
        srt = self.srt_path(recording_date, slug)
        md = self.md_path(recording_date, slug)
        txt = self.txt_path(recording_date, slug)
        raw = self.raw_json_path(recording_date, slug)

        from cheroki.core.exporter import to_markdown_with_frontmatter, to_srt, to_txt

        srt.write_text(to_srt(result.utterances), encoding="utf-8")
        md.write_text(
            to_markdown_with_frontmatter(
                result.utterances,
                result.metadata,
                frontmatter=frontmatter_extra or {},
            ),
            encoding="utf-8",
        )
        txt.write_text(to_txt(result.utterances), encoding="utf-8")
        raw.write_text(
            json.dumps(result.raw_response, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info("산출물 기록: %s / %s (4개 파일)", session_folder_name(recording_date), slug)
        return {"srt": srt, "md": md, "txt": txt, "raw": raw}
