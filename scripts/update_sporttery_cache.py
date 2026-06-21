"""Fetch sporttery odds from China network and update data/sporttery_cache.json."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arbitrage.config import settings
from arbitrage.fetchers.sporttery_web import fetch_sporttery_world_cup, save_sporttery_cache


async def main() -> None:
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        matches = await fetch_sporttery_world_cup(client)
    if not matches:
        raise SystemExit("体育彩票抓取失败，请在国内网络下重试")
    save_sporttery_cache(matches)
    print(f"已更新缓存：{len(matches)} 场 → data/sporttery_cache.json")


if __name__ == "__main__":
    asyncio.run(main())
