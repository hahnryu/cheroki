"""허용 사용자 전원에게 Telegram 공지 발송.

봇 프로세스가 내려가 있어도 작동한다. Telegram `sendMessage` API를
직접 호출하기 때문. 배포, 장애 공지, 모드 전환 알림 등에 쓴다.

사용:
  uv run python scripts/announce.py "🔧 2GB 모드 전환 중. 2~5분 응답 없음."

환경변수 (.env):
  BOT_TOKEN, ALLOWED_USER_IDS
  LOCAL_API_URL  # 설정돼 있으면 그 서버 사용, 아니면 클라우드
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import httpx

from cheroki.config import load_config, setup_logging

logger = logging.getLogger("cheroki.announce")


async def _send(
    client: httpx.AsyncClient, base_url: str, token: str, chat_id: int, text: str
) -> tuple[int, bool, str]:
    url = f"{base_url.rstrip('/')}/bot{token}/sendMessage"
    try:
        r = await client.post(url, json={"chat_id": chat_id, "text": text})
        ok = r.status_code == 200 and r.json().get("ok", False)
        desc = r.json().get("description") if not ok else ""
        return chat_id, ok, desc
    except Exception as exc:
        return chat_id, False, str(exc)


async def main_async(args: argparse.Namespace) -> int:
    cfg = load_config()
    setup_logging(cfg.log_level)

    if not cfg.bot_token:
        logger.error("BOT_TOKEN이 비어있습니다.")
        return 2
    if not cfg.allowed_user_ids:
        logger.error("ALLOWED_USER_IDS가 비어있습니다 - 받을 사람이 없습니다.")
        return 2

    base_url = (
        cfg.local_api_url.rstrip("/")
        if (args.prefer_local and cfg.local_api_url and cfg.local_api_url.strip())
        else "https://api.telegram.org"
    )

    logger.info(
        "공지 발송: %d명 대상 · 경유 %s",
        len(cfg.allowed_user_ids),
        base_url,
    )

    async with httpx.AsyncClient(timeout=15.0) as client:
        tasks = [
            _send(client, base_url, cfg.bot_token, uid, args.message)
            for uid in cfg.allowed_user_ids
        ]
        results = await asyncio.gather(*tasks)

    any_failed = False
    for uid, ok, desc in results:
        if ok:
            logger.info("  ✓ %d", uid)
        else:
            logger.warning("  ✗ %d - %s", uid, desc)
            any_failed = True
    return 1 if any_failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="허용 사용자에게 공지 발송")
    parser.add_argument("message", help="보낼 메시지 (필요시 따옴표로 감싸세요)")
    parser.add_argument(
        "--prefer-local",
        action="store_true",
        help="LOCAL_API_URL이 설정돼 있으면 클라우드 대신 로컬 서버 사용",
    )
    args = parser.parse_args()

    if not args.message.strip():
        print("메시지가 비었습니다.", file=sys.stderr)
        sys.exit(2)

    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
