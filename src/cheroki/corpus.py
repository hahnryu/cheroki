"""교정 쌍 코퍼스 관리 모듈."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cheroki.corrector import Correction


def save_corpus_pairs(
    file_id: str,
    corrections: list[Correction],
    corpus_dir: Path,
    source_file: str = "",
    language: str = "ko",
) -> Path:
    """교정 쌍을 코퍼스로 저장한다.

    각 교정 항목을 (원본, 교정) 쌍으로 누적.
    """
    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)

    pairs = []
    for corr in corrections:
        if corr.original_text.strip() == corr.corrected_text.strip():
            continue  # 변경 없는 항목은 저장하지 않음
        pairs.append({
            "original": corr.original_text,
            "corrected": corr.corrected_text,
            "segment_index": corr.segment_index,
        })

    if not pairs:
        return corpus_dir  # 저장할 쌍이 없음

    entry = {
        "file_id": file_id,
        "source_file": source_file,
        "language": language,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pairs": pairs,
    }

    out_path = corpus_dir / f"{file_id}.corpus.json"
    out_path.write_text(
        json.dumps(entry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def load_corpus_pairs(path: Path) -> dict[str, Any]:
    """코퍼스 파일 하나를 로드."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def count_corpus_pairs(corpus_dir: Path) -> int:
    """코퍼스 디렉토리의 총 교정 쌍 수를 반환."""
    corpus_dir = Path(corpus_dir)
    total = 0
    for path in corpus_dir.glob("*.corpus.json"):
        data = load_corpus_pairs(path)
        total += len(data.get("pairs", []))
    return total


def list_corpus_files(corpus_dir: Path) -> list[Path]:
    """코퍼스 디렉토리의 모든 코퍼스 파일을 반환."""
    return sorted(Path(corpus_dir).glob("*.corpus.json"))
