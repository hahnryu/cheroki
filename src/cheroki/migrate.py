"""레이아웃 마이그레이션.

이전 구조:
    data/uploads/<id>.<ext>
    data/exports/<id>.{srt, md, txt, raw.json}

새 구조:
    data/<YYMMDD>/<slug>_raw.<ext>
    data/<YYMMDD>/<slug>_raw.{srt, md, txt, json}

SQLite의 경로 컬럼도 새 경로로 업데이트한다. audio.raw.json → audio.json (확장자 정책 변경).

사용: python -m cheroki.migrate [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from cheroki.config import load_config, setup_logging
from cheroki.naming import build_slug, file_format_from_name
from cheroki.storage.fs_store import FileStore
from cheroki.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)


def run(*, dry_run: bool = False) -> int:
    setup_logging("INFO")
    config = load_config()
    db = SQLiteStore(config.db_path)
    fs = FileStore(config.data_dir)

    records = db.list_all()
    moved = 0
    skipped = 0
    errors = 0

    for record in records:
        try:
            if _migrate_one(record, db, fs, dry_run=dry_run):
                moved += 1
            else:
                skipped += 1
        except Exception:
            logger.exception("마이그레이션 실패: %s", record.get("id"))
            errors += 1

    logger.info(
        "마이그레이션 완료: 이동 %d / 스킵 %d / 에러 %d (dry_run=%s)",
        moved, skipped, errors, dry_run,
    )
    db.close()
    return errors


def _migrate_one(record: dict, db: SQLiteStore, fs: FileStore, *, dry_run: bool) -> bool:
    rec_id = record["id"]

    # 녹음 날짜: recording_date 있으면 그거, 없으면 received_at, 없으면 created_at
    recording_date = _pick_date(record)

    # 슬러그: romanized_slug 있으면 그거, 없으면 지금 생성
    slug = record.get("romanized_slug")
    if not slug:
        slug = build_slug(
            caption=record.get("caption"),
            original_filename=record.get("file_name"),
            record_id=rec_id,
        )

    old_audio = _path(record.get("audio_path"))
    old_srt = _path(record.get("srt_path"))
    old_md = _path(record.get("md_path"))
    old_txt = _path(record.get("txt_path"))
    old_raw = _path(record.get("raw_json_path"))

    # 하나도 옮길 파일이 없으면 메타데이터만 채움
    has_files = any(p and p.exists() for p in [old_audio, old_srt, old_md, old_txt, old_raw])
    if not has_files:
        if dry_run:
            logger.info("[dry] %s: 파일 없음, 메타만 업데이트 예정", rec_id)
        else:
            _update_metadata_only(db, rec_id, recording_date, slug, record)
        return False

    audio_suffix = (
        old_audio.suffix if old_audio and old_audio.exists()
        else (record.get("file_format") or file_format_from_name(record.get("file_name")) or ".bin")
    )

    new_audio = fs.audio_path(recording_date, slug, audio_suffix) if old_audio else None
    new_srt = fs.srt_path(recording_date, slug) if old_srt else None
    new_md = fs.md_path(recording_date, slug) if old_md else None
    new_txt = fs.txt_path(recording_date, slug) if old_txt else None
    new_raw = fs.raw_json_path(recording_date, slug) if old_raw else None

    moves: list[tuple[Path, Path]] = []
    for src, dst in [(old_audio, new_audio), (old_srt, new_srt),
                      (old_md, new_md), (old_txt, new_txt), (old_raw, new_raw)]:
        if src and dst and src.exists():
            moves.append((src, dst))

    if dry_run:
        logger.info("[dry] %s -> %s/%s_raw.*", rec_id, recording_date.strftime("%y%m%d"), slug)
        for src, dst in moves:
            logger.info("    %s -> %s", src, dst)
        return True

    for src, dst in moves:
        if src.resolve() == dst.resolve():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        logger.info("mv %s -> %s", src, dst)

    db.set_slug(rec_id, slug)
    db.update_paths(
        rec_id,
        audio_path=new_audio if new_audio and (new_audio.exists() or old_audio) else None,
        srt_path=new_srt if new_srt and (new_srt.exists() or old_srt) else None,
        md_path=new_md if new_md and (new_md.exists() or old_md) else None,
        txt_path=new_txt if new_txt and (new_txt.exists() or old_txt) else None,
        raw_json_path=new_raw if new_raw and (new_raw.exists() or old_raw) else None,
    )
    # recording_date, file_format 도 비어 있으면 채움
    db._conn.execute(
        """UPDATE transcripts
           SET recording_date = COALESCE(recording_date, ?),
               file_format = COALESCE(file_format, ?),
               source = COALESCE(source, 'telegram')
           WHERE id = ?""",
        (recording_date.isoformat(), audio_suffix, rec_id),
    )
    db._conn.commit()
    return True


def _update_metadata_only(db, rec_id, recording_date, slug, record) -> None:
    db.set_slug(rec_id, slug)
    db._conn.execute(
        """UPDATE transcripts
           SET recording_date = COALESCE(recording_date, ?),
               source = COALESCE(source, 'telegram')
           WHERE id = ?""",
        (recording_date.isoformat(), rec_id),
    )
    db._conn.commit()


def _path(value):
    if not value:
        return None
    return Path(str(value))


def _pick_date(record: dict):
    for key in ("recording_date", "received_at", "created_at"):
        raw = record.get(key)
        if not raw:
            continue
        try:
            if "T" in raw:
                dt = datetime.fromisoformat(raw)
                return dt.date()
            return datetime.fromisoformat(raw).date()
        except ValueError:
            continue
    return datetime.now(UTC).date()


def _cli() -> None:
    parser = argparse.ArgumentParser(prog="cheroki.migrate")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    _cli()
