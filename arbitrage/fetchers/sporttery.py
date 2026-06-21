from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from loguru import logger

from arbitrage.config import settings
from arbitrage.models import OddsEntry, utc_now


API_URL = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry"
PAGE_URL = "https://m.sporttery.cn/mjc/jsq/zqspf/"
BEIJING_TZ = timezone(timedelta(hours=8))


async def fetch_sporttery(client: httpx.AsyncClient) -> list[OddsEntry]:
    response = await client.get(
        API_URL,
        params={"channel": "c", "poolCode": "had"},
        headers={"Referer": PAGE_URL},
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        logger.warning("竞彩接口返回失败：{}", payload.get("errorMessage"))
        return []
    return _parse_payload(payload)


def _parse_payload(payload: dict) -> list[OddsEntry]:
    entries: list[OddsEntry] = []
    for match_day in payload.get("value", {}).get("matchInfoList", []):
        for match in match_day.get("subMatchList", []):
            entry = _parse_match(match)
            if entry:
                entries.append(entry)
    return entries


def _parse_match(match: dict) -> OddsEntry | None:
    had = match.get("had")
    if not isinstance(had, dict) or not had:
        return None

    odds_home = _parse_odds(had.get("h"))
    odds_draw = _parse_odds(had.get("d"))
    odds_away = _parse_odds(had.get("a"))
    if odds_home is None or odds_draw is None or odds_away is None:
        return None

    kickoff_time = _parse_kickoff(match.get("matchDate"), match.get("matchTime"))
    if kickoff_time is None:
        return None

    fetched_at = utc_now()
    return OddsEntry(
        platform="sporttery",
        match_id="",
        home_team=str(match.get("homeTeamAllName") or match.get("homeTeamAbbName") or ""),
        away_team=str(match.get("awayTeamAllName") or match.get("awayTeamAbbName") or ""),
        kickoff_time=kickoff_time,
        fetched_at=fetched_at,
        odds_home=odds_home,
        odds_draw=odds_draw,
        odds_away=odds_away,
        raw_odds_home=odds_home,
        raw_odds_draw=odds_draw,
        raw_odds_away=odds_away,
        source_id=str(match.get("matchId") or ""),
        source_url=PAGE_URL,
        metadata={
            "league": match.get("leagueAllName") or match.get("leagueAbbName"),
            "match_num": match.get("matchNumStr"),
            "update_date": had.get("updateDate"),
            "update_time": had.get("updateTime"),
        },
    )


def _parse_odds(value) -> float | None:
    try:
        odds = float(value)
    except (TypeError, ValueError):
        return None
    return odds if odds > 1 else None


def _parse_kickoff(match_date: str | None, match_time: str | None):
    if not match_date or not match_time:
        return None
    try:
        local_time = datetime.fromisoformat(f"{match_date}T{match_time}").replace(
            tzinfo=BEIJING_TZ
        )
    except ValueError:
        return None
    return local_time.astimezone(timezone.utc)

