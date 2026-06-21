from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx
from loguru import logger

from arbitrage.config import settings
from arbitrage.core.fees import smarkets_effective_odds
from arbitrage.fetchers.utils import parse_datetime, parse_matchup
from arbitrage.models import OddsEntry, utc_now


EVENTS_URL = "https://api.smarkets.com/v3/events/"


async def fetch_smarkets(client: httpx.AsyncClient) -> list[OddsEntry]:
    response = await client.get(
        EVENTS_URL,
        params={"type": "football_match", "state": "upcoming", "limit": "100"},
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()
    events = _items(response.json(), "events")

    candidate_events = [event for event in events if _event_in_kickoff_window(event)]

    entries: list[OddsEntry] = []
    for event in candidate_events:
        await asyncio.sleep(settings.smarkets_event_delay_seconds)
        try:
            entry = await _fetch_event_entry(client, event)
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning("Smarkets 赛事 {} 抓取失败：{}", event.get("id"), exc)
            continue
        if entry:
            entries.append(entry)
    return entries


async def _fetch_event_entry(client: httpx.AsyncClient, event: dict) -> OddsEntry | None:
    event_id = str(event.get("id") or "")
    if not event_id:
        return None

    markets_response = await _get_with_backoff(
        client, f"https://api.smarkets.com/v3/events/{event_id}/markets/"
    )
    markets_response.raise_for_status()
    markets = _items(markets_response.json(), "markets")
    winner_market = next((market for market in markets if _is_winner_3_way(market)), None)
    if not winner_market:
        return None

    market_id = str(winner_market.get("id") or "")
    contracts_response = await _get_with_backoff(
        client, f"https://api.smarkets.com/v3/markets/{market_id}/contracts/"
    )
    contracts_response.raise_for_status()
    contracts = _items(contracts_response.json(), "contracts")

    quotes_response = await _get_with_backoff(
        client, f"https://api.smarkets.com/v3/markets/{market_id}/quotes/"
    )
    quotes_response.raise_for_status()
    quotes = quotes_response.json()

    odds_by_contract = _extract_contract_odds(contracts, quotes)
    if not {"home", "draw", "away"}.issubset(odds_by_contract):
        logger.debug("跳过 Smarkets 赛事 {}，未找到完整胜平负报价", event_id)
        return None

    name = str(event.get("name") or event.get("short_name") or "")
    matchup = parse_matchup(name)
    if not matchup:
        return None

    kickoff = parse_datetime(
        event.get("start_datetime") or event.get("start_date") or event.get("start")
    )
    if not kickoff:
        return None

    home_team, away_team = matchup
    raw_home = odds_by_contract["home"]
    raw_draw = odds_by_contract["draw"]
    raw_away = odds_by_contract["away"]
    return OddsEntry(
        platform="smarkets",
        match_id="",
        home_team=home_team,
        away_team=away_team,
        kickoff_time=kickoff,
        fetched_at=utc_now(),
        odds_home=smarkets_effective_odds(raw_home),
        odds_draw=smarkets_effective_odds(raw_draw),
        odds_away=smarkets_effective_odds(raw_away),
        raw_odds_home=raw_home,
        raw_odds_draw=raw_draw,
        raw_odds_away=raw_away,
        source_id=event_id,
        source_url=_event_url(event),
        metadata={"event_name": name, "market_id": market_id},
    )


def _is_winner_3_way(market: dict) -> bool:
    market_type = market.get("market_type")
    market_type_name = ""
    if isinstance(market_type, dict):
        market_type_name = str(market_type.get("name") or "")
    elif market_type:
        market_type_name = str(market_type)

    return (
        market.get("category") == "winner"
        and str(market.get("name") or "").casefold() == "full-time result"
        and market_type_name == "WINNER_3_WAY"
    )


def _event_url(event: dict) -> str | None:
    full_slug = event.get("full_slug")
    if not full_slug:
        return None
    return f"https://smarkets.com{full_slug}"


async def _get_with_backoff(client: httpx.AsyncClient, url: str) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = await client.get(url, timeout=settings.request_timeout_seconds)
            if response.status_code == 429:
                retry_after = response.headers.get("retry-after")
                delay = float(retry_after) if retry_after else 2.0 * (attempt + 1)
                await asyncio.sleep(delay)
                response.raise_for_status()
            response.raise_for_status()
            return response
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_error = exc
            await asyncio.sleep(1.0 * (attempt + 1))

    if last_error:
        raise last_error
    raise RuntimeError(f"failed to fetch {url}")


def _event_in_kickoff_window(event: dict) -> bool:
    slug_filter = settings.smarkets_event_slug_filter.casefold().strip()
    if slug_filter and slug_filter not in str(event.get("full_slug") or "").casefold():
        return False

    kickoff = parse_datetime(
        event.get("start_datetime") or event.get("start_date") or event.get("start")
    )
    if kickoff is None:
        return False

    now = utc_now()
    min_kickoff = now + timedelta(hours=settings.min_kickoff_hours)
    max_kickoff = now + timedelta(hours=settings.max_kickoff_hours)
    return min_kickoff <= kickoff <= max_kickoff


def _extract_contract_odds(contracts: list[dict], quotes: dict) -> dict[str, float]:
    result: dict[str, float] = {}
    for contract in contracts:
        outcome = _contract_outcome(contract)
        if outcome is None:
            continue
        contract_id = str(contract.get("id") or "")
        quote = quotes.get(contract_id)
        if not isinstance(quote, dict):
            continue
        raw_odds = _raw_odds_from_quote(quote)
        if raw_odds:
            result[outcome] = raw_odds
    return result


def _contract_outcome(contract: dict) -> str | None:
    contract_type = contract.get("contract_type")
    if isinstance(contract_type, dict):
        name = str(contract_type.get("name") or "").casefold()
    else:
        name = str(contract.get("slug") or contract_type or "").casefold()

    if name == "home":
        return "home"
    if name == "draw":
        return "draw"
    if name == "away":
        return "away"
    return None


def _raw_odds_from_quote(quote: dict) -> float | None:
    offers = quote.get("offers")
    if not isinstance(offers, list) or not offers:
        return None

    prices = [
        item.get("price")
        for item in offers
        if isinstance(item, dict) and isinstance(item.get("price"), int)
    ]
    if not prices:
        return None

    best_price = min(prices)
    if best_price <= 0 or best_price >= 10000:
        return None
    return 10000 / best_price


def _items(payload, key: str) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        value = payload.get(key) or payload.get("data") or []
        return value if isinstance(value, list) else []
    return []

