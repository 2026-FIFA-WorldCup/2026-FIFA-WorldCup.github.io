from __future__ import annotations

import httpx
from loguru import logger

from arbitrage.config import settings
from arbitrage.core.fees import odds_from_probability, polymarket_effective_odds
from arbitrage.fetchers.utils import ensure_list, parse_datetime, parse_float, parse_matchup
from arbitrage.models import OddsEntry, utc_now


EVENTS_URL = "https://gamma-api.polymarket.com/events"
SOCCER_TAG_ID = "100350"
PAGE_LIMIT = 50
MAX_OFFSET = 300


async def fetch_polymarket(client: httpx.AsyncClient) -> list[OddsEntry]:
    entries: list[OddsEntry] = []
    for offset in range(0, MAX_OFFSET, PAGE_LIMIT):
        response = await client.get(
            EVENTS_URL,
            params={
                "active": "true",
                "closed": "false",
                "tag_id": SOCCER_TAG_ID,
                "limit": str(PAGE_LIMIT),
                "offset": str(offset),
            },
            timeout=settings.request_timeout_seconds,
        )
        response.raise_for_status()
        events = response.json()
        if isinstance(events, dict):
            events = events.get("data") or events.get("events") or []
        if not events:
            break
        for event in events:
            try:
                entry = _parse_event(event)
            except ValueError as exc:
                logger.debug("跳过 Polymarket 事件: {}", exc)
                continue
            if entry:
                entries.append(entry)
    return entries


def _parse_event(event: dict) -> OddsEntry | None:
    title = str(event.get("title") or "")
    if " - " in title:
        return None

    matchup = parse_matchup(title)
    if not matchup:
        return None

    kickoff = parse_datetime(event.get("endDate") or event.get("end_date"))
    if not kickoff:
        return None

    home_team, away_team = matchup
    market_prices = _extract_three_way_prices(event.get("markets") or [], home_team, away_team)
    if not {"home", "draw", "away"}.issubset(market_prices):
        return None

    home_probability = market_prices["home"]
    draw_probability = market_prices["draw"]
    away_probability = market_prices["away"]
    return OddsEntry(
        platform="polymarket",
        match_id="",
        home_team=home_team,
        away_team=away_team,
        kickoff_time=kickoff,
        fetched_at=utc_now(),
        odds_home=polymarket_effective_odds(home_probability),
        odds_draw=polymarket_effective_odds(draw_probability),
        odds_away=polymarket_effective_odds(away_probability),
        raw_odds_home=odds_from_probability(home_probability),
        raw_odds_draw=odds_from_probability(draw_probability),
        raw_odds_away=odds_from_probability(away_probability),
        source_id=str(event.get("id") or ""),
        source_url=f"https://polymarket.com/event/{event.get('slug')}",
        metadata={"title": title, "slug": event.get("slug")},
    )


def _extract_three_way_prices(
    markets: list[dict], home_team: str, away_team: str
) -> dict[str, float]:
    prices_by_outcome: dict[str, float] = {}
    for market in markets:
        if market.get("closed") or not market.get("active", True):
            continue
        outcome = _market_outcome(market, home_team, away_team)
        if outcome is None:
            continue
        yes_probability = _yes_probability(market)
        if yes_probability is not None:
            prices_by_outcome[outcome] = yes_probability
    return prices_by_outcome


def _market_outcome(market: dict, home_team: str, away_team: str) -> str | None:
    label = str(market.get("groupItemTitle") or market.get("question") or "").casefold()
    home = home_team.casefold()
    away = away_team.casefold()
    if "draw" in label:
        return "draw"
    if label == home or f"will {home} win" in label:
        return "home"
    if label == away or f"will {away} win" in label:
        return "away"
    return None


def _yes_probability(market: dict) -> float | None:
    outcomes = [str(item).casefold() for item in ensure_list(market.get("outcomes"))]
    prices = [parse_float(item) for item in ensure_list(market.get("outcomePrices"))]
    if len(outcomes) != len(prices) or not prices:
        return None

    for outcome, price in zip(outcomes, prices):
        if price is None or price >= 1:
            continue
        if outcome == "yes":
            return price
    return None

