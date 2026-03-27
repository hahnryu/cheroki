"""음성 파일 저장/관리 모듈."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".opus"}


def is_audio_file(path: Path) -> bool:
    """지원하는 음성 파일인지 확인."""
    return path.suffix.lower() in AUDIO_EXTENSIONS


def file_hash(path: Path) -> str:
    """파일의 SHA-256 해시를 반환."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def store_original(source: Path, originals_dir: Path) -> dict[str, Any]:
    """원본 음성 파일을 originals/로 복사하고 메타데이터를 기록한다.

    Returns:
        메타데이터 dict (file_id, original_name, hash, stored_path 등)
    """
    source = Path(source)
    originals_dir = Path(originals_dir)
    originals_dir.mkdir(parents=True, exist_ok=True)

    if not source.is_file():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {source}")

    if not is_audio_file(source):
        raise ValueError(f"지원하지 않는 형식입니다: {source.suffix}")

    # 파일 ID: 타임스탬프 + 원본 이름
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    file_id = f"{timestamp}_{source.stem}"

    # 복사
    dest = originals_dir / f"{file_id}{source.suffix}"
    shutil.copy2(source, dest)

    # 해시 검증
    src_hash = file_hash(source)
    dest_hash = file_hash(dest)
    if src_hash != dest_hash:
        dest.unlink()
        raise RuntimeError("파일 복사 후 해시 불일치 — 원본 손상 가능성")

    # 메타데이터
    metadata = {
        "file_id": file_id,
        "original_name": source.name,
        "stored_path": str(dest),
        "sha256": src_hash,
        "size_bytes": source.stat().st_size,
        "stored_at": now.isoformat(),
    }

    meta_path = originals_dir / f"{file_id}.meta.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    return metadata


def load_metadata(meta_path: Path) -> dict[str, Any]:
    """메타데이터 JSON을 로드."""
    return json.loads(meta_path.read_text(encoding="utf-8"))
