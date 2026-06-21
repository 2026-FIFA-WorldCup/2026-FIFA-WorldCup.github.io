from __future__ import annotations

import httpx
from loguru import logger

from arbitrage.config import settings
from arbitrage.core.fees import kalshi_effective_odds, odds_from_probability
from arbitrage.fetchers.utils import parse_datetime, parse_float, parse_matchup
from arbitrage.models import OddsEntry, utc_now


API_URL = "https://trading-api.kalshi.com/trade-api/v2/markets"


async def fetch_kalshi(client: httpx.AsyncClient) -> list[OddsEntry]:
    if not settings.kalshi_api_key:
        logger.warning("未配置 KALSHI_API_KEY，跳过 Kalshi")
        return []

    response = await client.get(
        API_URL,
        params={"category": "Sports", "limit": "100"},
        headers={"Authorization": f"Bearer {settings.kalshi_api_key}"},
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    markets = payload.get("markets") or payload.get("data") or []

    entries: list[OddsEntry] = []
    for market in markets:
        title = str(market.get("title") or market.get("subtitle") or "")
        if "soccer" not in title.casefold() and "football" not in title.casefold():
            continue
        entry = _parse_market(market)
        if entry:
            entries.append(entry)
    return entries


def _parse_market(market: dict) -> OddsEntry | None:
    title = str(market.get("title") or "")
    matchup = parse_matchup(title)
    if not matchup:
        return None

    yes_ask = _parse_probability_price(market.get("yes_ask"))
    no_ask = _parse_probability_price(market.get("no_ask"))
    if yes_ask is None or no_ask is None:
        return None

    fee_multiplier = parse_float(market.get("fee_multiplier")) or 0.07
    kickoff = parse_datetime(market.get("close_time") or market.get("expiration_time"))
    if not kickoff:
        return None

    home_team, away_team = matchup
    return OddsEntry(
        platform="kalshi",
        match_id="",
        home_team=home_team,
        away_team=away_team,
        kickoff_time=kickoff,
        fetched_at=utc_now(),
        odds_home=kalshi_effective_odds(yes_ask, fee_multiplier),
        odds_not_home=kalshi_effective_odds(no_ask, fee_multiplier),
        raw_odds_home=odds_from_probability(yes_ask),
        raw_odds_not_home=odds_from_probability(no_ask),
        source_id=str(market.get("ticker") or ""),
        metadata={"title": title, "fee_multiplier": fee_multiplier},
    )


def _parse_probability_price(value) -> float | None:
    number = parse_float(value)
    if number is None:
        return None
    if number > 1:
        number = number / 100
    if number <= 0 or number >= 1:
        return None
    return number

