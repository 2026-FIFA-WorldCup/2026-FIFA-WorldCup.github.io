from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta
from typing import Awaitable, Callable

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from arbitrage.config import settings
from arbitrage.core.calculator import find_arbitrage_opportunities
from arbitrage.core.matcher import match_entries
from arbitrage.display import print_scan_summary
from arbitrage.fetchers.kalshi import fetch_kalshi
from arbitrage.fetchers.polymarket import fetch_polymarket
from arbitrage.fetchers.smarkets import fetch_smarkets
from arbitrage.fetchers.sporttery import fetch_sporttery
from arbitrage.models import OddsEntry, utc_now
from arbitrage.storage import write_scan_logs


Fetcher = tuple[str, Callable[[httpx.AsyncClient], Awaitable[list[OddsEntry]]]]


FETCHERS: list[Fetcher] = [
    ("polymarket", fetch_polymarket),
    ("smarkets", fetch_smarkets),
    ("sporttery", fetch_sporttery),
]


async def scan_once() -> None:
    async with httpx.AsyncClient(
        headers={"User-Agent": "football-arbitrage-detector/0.1"}
    ) as client:
        fetchers = _enabled_fetchers()
        results = await asyncio.gather(
            *[_run_fetcher(name, fetcher, client) for name, fetcher in fetchers]
        )

    entries = [entry for platform_entries in results for entry in platform_entries]
    entries = _filter_kickoff_window(entries)
    groups = match_entries(entries)
    opportunities = find_arbitrage_opportunities(groups)
    write_scan_logs(entries, opportunities)
    print_scan_summary(len(groups), opportunities)


async def _run_fetcher(name: str, fetcher, client: httpx.AsyncClient) -> list[OddsEntry]:
    try:
        entries = await fetcher(client)
        logger.info("{} 抓取完成：{} 条赔率", name, len(entries))
        return entries
    except Exception as exc:
        logger.warning("{} 抓取失败：{}", name, exc)
        return []


def _enabled_fetchers() -> list[Fetcher]:
    fetchers = list(FETCHERS)
    if settings.kalshi_api_key:
        fetchers.append(("kalshi", fetch_kalshi))
    return fetchers


def _filter_kickoff_window(entries: list[OddsEntry]) -> list[OddsEntry]:
    now = utc_now()
    min_kickoff = now + timedelta(hours=settings.min_kickoff_hours)
    max_kickoff = now + timedelta(hours=settings.max_kickoff_hours)
    return [
        entry
        for entry in entries
        if min_kickoff <= entry.kickoff_time <= max_kickoff
    ]


async def run_scheduler() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scan_once,
        "interval",
        seconds=settings.refresh_interval_seconds,
        next_run_time=utc_now(),
        max_instances=1,
    )
    scheduler.start()
    logger.info("调度器已启动，每 {} 秒扫描一次", settings.refresh_interval_seconds)
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        scheduler.shutdown()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="足球赔率套利检测器")
    parser.add_argument("--once", action="store_true", help="只扫描一次后退出")
    return parser.parse_args()


def main() -> None:
    _configure_console_encoding()
    args = parse_args()
    if args.once:
        asyncio.run(scan_once())
    else:
        asyncio.run(run_scheduler())


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()

