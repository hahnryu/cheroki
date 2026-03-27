"""교정 반영 모듈."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cheroki.transcriber import TranscriptionResult, Segment


@dataclass
class Correction:
    """단일 교정 항목."""
    segment_index: int
    original_text: str
    corrected_text: str
    corrected_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CorrectionSet:
    """하나의 전사에 대한 교정 모음."""
    file_id: str
    corrections: list[Correction]
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "created_at": self.created_at,
            "corrections": [c.to_dict() for c in self.corrections],
        }


def apply_corrections(
    result: TranscriptionResult,
    corrections: list[Correction],
) -> TranscriptionResult:
    """교정을 적용하여 새 TranscriptionResult를 반환한다. 원본은 변경하지 않는다."""
    corrected = deepcopy(result)

    for corr in corrections:
        idx = corr.segment_index
        if 0 <= idx < len(corrected.segments):
            corrected.segments[idx] = Segment(
                start=corrected.segments[idx].start,
                end=corrected.segments[idx].end,
                text=corr.corrected_text,
                confidence=1.0,  # 사람이 교정한 것은 confidence 1.0
            )

    return corrected


def save_corrections(
    correction_set: CorrectionSet,
    corrections_dir: Path,
) -> Path:
    """교정 세트를 JSON으로 저장."""
    corrections_dir = Path(corrections_dir)
    corrections_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    correction_set.created_at = now.isoformat()
    for c in correction_set.corrections:
        if not c.corrected_at:
            c.corrected_at = now.isoformat()

    out_path = corrections_dir / f"{correction_set.file_id}.corrections.json"
    out_path.write_text(
        json.dumps(correction_set.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def load_corrections(path: Path) -> CorrectionSet:
    """저장된 교정 세트를 로드."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    corrections = [
        Correction(
            segment_index=c["segment_index"],
            original_text=c["original_text"],
            corrected_text=c["corrected_text"],
            corrected_at=c.get("corrected_at", ""),
        )
        for c in data.get("corrections", [])
    ]
    return CorrectionSet(
        file_id=data["file_id"],
        corrections=corrections,
        created_at=data.get("created_at", ""),
    )
