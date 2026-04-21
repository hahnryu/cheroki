"""STT provider 비교 실험.

동일 오디오 파일을 Deepgram과 ElevenLabs Scribe로 동시 전사한다.
결과는 오디오와 같은 폴더에 provider 접미사를 붙여 저장:

  <stem>.deepgram.{srt,md,txt,raw.json}
  <stem>.scribe.{srt,md,txt,raw.json}

SQLite는 건드리지 않는다. 이 스크립트는 Task 18(provider 비교 실험) 용도의
사이드 트랙으로 정식 저장 파이프라인과 분리되어 있다.

사용:
  uv run python scripts/compare_providers.py data/260420/rwgr66_raw.ogg
  uv run python scripts/compare_providers.py audio.m4a --out /tmp/compare

환경변수 (.env):
  DEEPGRAM_API_KEY, DEEPGRAM_MODEL
  ELEVENLABS_API_KEY, ELEVENLABS_MODEL
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path

from cheroki.config import load_config, setup_logging
from cheroki.core.result import TranscriptionResult
from cheroki.core.transcribers import DeepgramTranscriber, ScribeTranscriber
from cheroki.core.transcribers.base import Transcriber

logger = logging.getLogger("cheroki.compare")


async def _run_one(
    name: str,
    transcriber: Transcriber,
    audio_path: Path,
    out_dir: Path,
) -> tuple[str, TranscriptionResult | None, float, str | None]:
    stem = audio_path.stem
    t0 = time.monotonic()
    try:
        result = await transcriber.transcribe(audio_path)
    except Exception as exc:
        elapsed = time.monotonic() - t0
        logger.exception("%s 실패 (%.1fs)", name, elapsed)
        return name, None, elapsed, str(exc)

    elapsed = time.monotonic() - t0

    (out_dir / f"{stem}.{name}.srt").write_text(result.to_srt(), encoding="utf-8")
    (out_dir / f"{stem}.{name}.md").write_text(result.to_markdown(), encoding="utf-8")
    (out_dir / f"{stem}.{name}.txt").write_text(result.to_txt(), encoding="utf-8")
    (out_dir / f"{stem}.{name}.raw.json").write_text(
        json.dumps(result.raw_response, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return name, result, elapsed, None


def _format_summary(
    name: str,
    result: TranscriptionResult | None,
    elapsed: float,
    err: str | None,
) -> str:
    if err or result is None:
        msg = (err or "unknown error")[:200]
        return f"  [{name:<9}] FAILED after {elapsed:6.1f}s  {msg}"
    m = result.metadata
    return (
        f"  [{name:<9}] {elapsed:6.1f}s  "
        f"audio {m.duration_sec:6.1f}s  "
        f"speakers {m.speaker_count}  "
        f"utterances {len(result.utterances):>4}  "
        f"model={m.model}"
    )


async def main_async(args: argparse.Namespace) -> int:
    cfg = load_config()
    setup_logging(cfg.log_level)

    audio_path = Path(args.audio).resolve()
    if not audio_path.exists():
        logger.error("오디오 파일 없음: %s", audio_path)
        return 2

    out_dir = Path(args.out).resolve() if args.out else audio_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    providers: list[tuple[str, Transcriber]] = []
    if cfg.deepgram_api_key and not args.skip_deepgram:
        providers.append((
            "deepgram",
            DeepgramTranscriber(
                api_key=cfg.deepgram_api_key,
                model=cfg.deepgram_model,
            ),
        ))
    else:
        logger.info("deepgram 건너뜀 (키 없음 또는 --skip-deepgram)")

    if cfg.elevenlabs_api_key and not args.skip_scribe:
        providers.append((
            "scribe",
            ScribeTranscriber(
                api_key=cfg.elevenlabs_api_key,
                model=cfg.elevenlabs_model,
            ),
        ))
    else:
        logger.info("scribe 건너뜀 (키 없음 또는 --skip-scribe)")

    if not providers:
        logger.error("활성화된 provider가 없습니다. .env 키를 확인하세요.")
        return 2

    logger.info(
        "비교 시작: %s (%.1f MB) · providers=%s · out=%s",
        audio_path.name,
        audio_path.stat().st_size / 1e6,
        [n for n, _ in providers],
        out_dir,
    )

    tasks = [_run_one(name, tr, audio_path, out_dir) for name, tr in providers]
    outcomes = await asyncio.gather(*tasks)

    print()
    print(f"=== 비교 요약 · {audio_path.name} ===")
    for name, result, elapsed, err in outcomes:
        print(_format_summary(name, result, elapsed, err))
    print()
    print(f"결과 파일: {out_dir}")

    any_failed = any(err for _, _, _, err in outcomes)
    return 1 if any_failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="STT provider 비교 실험 (Deepgram vs Scribe)")
    parser.add_argument("audio", help="비교할 오디오 파일 경로")
    parser.add_argument("--out", help="결과 저장 폴더 (기본: 오디오와 같은 폴더)")
    parser.add_argument("--skip-deepgram", action="store_true", help="Deepgram 건너뜀")
    parser.add_argument("--skip-scribe", action="store_true", help="Scribe 건너뜀")
    args = parser.parse_args()

    exit_code = asyncio.run(main_async(args))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
