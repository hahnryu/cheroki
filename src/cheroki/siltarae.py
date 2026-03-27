"""Siltarae 연동 어댑터 — 최종 녹취록을 Fragment 형식으로 변환/전송."""

from __future__ import annotations

import json
import structlog
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cheroki.transcriber import TranscriptionResult

logger = structlog.get_logger()


@dataclass
class Fragment:
    """Siltarae Fragment — 음성 전사에서 추출된 지식 단위.

    Siltarae는 음성에서 추출한 내용을 Fragment 단위로 관리한다.
    각 Fragment는 원본 소스, 타임스탬프, 텍스트, 메타데이터를 포함한다.
    """
    source_id: str          # cheroki file_id
    source_type: str = "audio_transcription"
    text: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    speaker: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def transcription_to_fragments(
    result: TranscriptionResult,
    file_id: str,
    metadata: dict[str, Any] | None = None,
) -> list[Fragment]:
    """TranscriptionResult를 Fragment 리스트로 변환한다.

    각 세그먼트가 하나의 Fragment가 된다.
    """
    meta = metadata or {}
    fragments: list[Fragment] = []

    for seg in result.segments:
        speaker = getattr(seg, "speaker", "") or ""
        frag = Fragment(
            source_id=file_id,
            text=seg.text.strip(),
            start_time=seg.start,
            end_time=seg.end,
            speaker=speaker,
            metadata={
                "confidence": seg.confidence,
                "language": result.language,
                "source_file": result.source_file,
                **meta,
            },
        )
        fragments.append(frag)

    return fragments


def save_fragments(
    fragments: list[Fragment],
    output_dir: Path,
    file_id: str,
) -> Path:
    """Fragment 리스트를 JSON으로 저장한다."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / f"{file_id}.fragments.json"
    data = [f.to_dict() for f in fragments]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("fragments_saved", file_id=file_id, count=len(fragments), path=str(path))
    return path


class SiltaraeClient:
    """Siltarae API 클라이언트.

    설정에 api_url이 있으면 HTTP 전송, 없으면 로컬 파일 저장.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        siltarae_cfg = config.get("siltarae", {})
        self.api_url: str = siltarae_cfg.get("api_url", "")
        self.api_key: str = siltarae_cfg.get("api_key", "")
        self.exports_dir = Path(config["paths"]["exports"])

    def send(
        self,
        result: TranscriptionResult,
        file_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Fragment를 Siltarae로 전송한다.

        API가 설정되지 않으면 로컬 파일로 저장.
        """
        fragments = transcription_to_fragments(result, file_id, metadata)

        if self.api_url:
            return self._send_http(fragments, file_id)

        # 로컬 저장 fallback
        path = save_fragments(fragments, self.exports_dir, file_id)
        return {
            "status": "local",
            "path": str(path),
            "fragment_count": len(fragments),
        }

    def _send_http(self, fragments: list[Fragment], file_id: str) -> dict[str, Any]:
        """HTTP로 Fragment 전송 (Siltarae API 연동 시)."""
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "file_id": file_id,
            "fragments": [f.to_dict() for f in fragments],
        }, ensure_ascii=False).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            self.api_url,
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                logger.info("siltarae_sent", file_id=file_id, fragments=len(fragments))
                return {"status": "sent", "response": body, "fragment_count": len(fragments)}
        except urllib.error.URLError as e:
            logger.error("siltarae_send_error", file_id=file_id, error=str(e))
            # fallback: 로컬 저장
            path = save_fragments(fragments, self.exports_dir, file_id)
            return {
                "status": "error_fallback_local",
                "error": str(e),
                "path": str(path),
                "fragment_count": len(fragments),
            }
