"""CLI 인터페이스.

사용:
    cheroki transcribe <audio_file> [options]
    cheroki bot                     # Telegram 봇 기동
    cheroki migrate                 # 기존 레이아웃 -> 새 레이아웃 이주
    cheroki info <record_id>        # 레코드 상세 조회

options (transcribe):
    --caption TEXT      캡션 자유형식 (날짜 힌트는 자동 파싱)
    --date YYMMDD       녹음 날짜 강제 지정 (캡션 파싱보다 우선)
    --title TEXT        제목 강제 지정
    --place TEXT        장소 (프론트매터/DB에 기록)
    --out DIR           DATA_DIR override
    --no-save           SQLite·파일시스템 저장 생략, stdout에만 출력
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from cheroki.config import load_config, setup_logging
from cheroki.core.transcribe import transcribe_audio
from cheroki.naming import build_slug, file_format_from_name, parse_recording_date
from cheroki.storage.fs_store import FileStore
from cheroki.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog="cheroki", description="cheroki CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("transcribe", help="오디오 파일 하나 녹취")
    t.add_argument("audio", type=Path, help="오디오/비디오 파일 경로")
    t.add_argument("--caption", type=str, default=None, help="자유형식 캡션")
    t.add_argument("--date", type=str, default=None, help="녹음 날짜 YYMMDD 또는 YYYY-MM-DD")
    t.add_argument("--title", type=str, default=None, help="제목 강제 지정")
    t.add_argument("--place", type=str, default=None, help="장소")
    t.add_argument("--out", type=Path, default=None, help="DATA_DIR override")
    t.add_argument("--no-save", action="store_true", help="저장 생략, stdout에만 출력")

    sub.add_parser("bot", help="Telegram 봇 기동")

    m = sub.add_parser("migrate", help="이전 레이아웃의 파일들을 새 레이아웃으로 이주")
    m.add_argument("--dry-run", action="store_true", help="이동 없이 계획만 출력")

    info_p = sub.add_parser("info", help="레코드 상세")
    info_p.add_argument("record_id", type=str)

    args = parser.parse_args()

    if args.cmd == "transcribe":
        asyncio.run(_cmd_transcribe(args))
    elif args.cmd == "bot":
        from cheroki.interfaces.telegram.__main__ import main as bot_main
        bot_main()
    elif args.cmd == "migrate":
        from cheroki.migrate import run as migrate_run
        migrate_run(dry_run=args.dry_run)
    elif args.cmd == "info":
        _cmd_info(args)


async def _cmd_transcribe(args: argparse.Namespace) -> None:
    setup_logging("INFO")
    config = load_config()

    if not args.audio.exists():
        print(f"파일이 없습니다: {args.audio}", file=sys.stderr)
        sys.exit(1)

    recording_date = _resolve_date(args.date, args.caption, args.audio)
    file_name = args.audio.name
    file_format = file_format_from_name(file_name)
    caption = args.caption
    title = args.title or caption or args.audio.stem

    data_dir = Path(args.out) if args.out else config.data_dir
    fs = FileStore(data_dir)

    # 녹취 먼저 실행 (저장 여부와 무관)
    logger.info("녹취 시작: %s", args.audio)
    result = await transcribe_audio(args.audio)

    if args.no_save:
        print(result.to_markdown(title=title))
        return

    db = SQLiteStore(config.db_path)
    rec_id = db.create_pending(
        file_name=file_name,
        file_size_bytes=args.audio.stat().st_size,
        file_format=file_format,
        caption=caption,
        session_title=title,
        recording_date=recording_date,
        place=args.place,
        source="cli",
    )
    slug = build_slug(caption=caption or title, original_filename=file_name, record_id=rec_id)
    db.set_slug(rec_id, slug)

    # 원본 오디오를 새 레이아웃 위치로 복사
    dest_audio = fs.audio_path(recording_date, slug, args.audio.suffix)
    if dest_audio.resolve() != args.audio.resolve():
        dest_audio.write_bytes(args.audio.read_bytes())
    db.set_audio_path(rec_id, dest_audio)
    db.set_processing(rec_id)

    frontmatter = {
        "title": title,
        "recording_date": recording_date.isoformat(),
        "record_id": rec_id,
        "slug": slug,
        "source": "cli",
        "caption": caption,
        "original_filename": file_name,
        "file_format": file_format,
        "place": args.place,
    }
    paths = fs.write_exports(recording_date, slug, result, frontmatter_extra=frontmatter)
    db.complete(
        rec_id,
        result=result,
        srt_path=paths["srt"],
        md_path=paths["md"],
        txt_path=paths["txt"],
        raw_json_path=paths["raw"],
    )
    db.close()

    print(f"완료: {rec_id}")
    print(f"  폴더: {paths['md'].parent}")
    print(f"  길이: {result.duration_sec:.0f}초, 화자 {result.speaker_count}명")
    for key in ("srt", "md", "txt", "raw"):
        print(f"  {key}: {paths[key]}")


def _resolve_date(date_arg: str | None, caption: str | None, audio_path: Path) -> date:
    if date_arg:
        # YYMMDD, YYYY-MM-DD, YYYY.MM.DD 등 지원
        parsed = parse_recording_date(date_arg, fallback=None)
        if parsed != date.today() or date_arg.startswith(date.today().strftime("%y%m%d")):
            return parsed
    # 캡션에서 추출, 없으면 파일 mtime, 최종은 today
    mtime = datetime.fromtimestamp(audio_path.stat().st_mtime, tz=UTC)
    return parse_recording_date(caption, fallback=mtime)


def _cmd_info(args: argparse.Namespace) -> None:
    config = load_config()
    db = SQLiteStore(config.db_path)
    record = db.get(args.record_id)
    db.close()
    if not record:
        print(f"레코드 없음: {args.record_id}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
