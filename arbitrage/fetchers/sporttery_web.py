from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from loguru import logger

from arbitrage.config import settings


API_URL = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry"
PAGE_URL = "https://m.sporttery.cn/mjc/jsq/zqspf/"
BEIJING_TZ = timezone(timedelta(hours=8))


@dataclass
class SportteryThreeWay:
    home: float
    draw: float
    away: float


@dataclass
class SportteryHandicap:
    goal_line: str
    label: str
    home: float
    draw: float
    away: float


@dataclass
class SportteryMatch:
    match_id: str
    home_team_zh: str
    away_team_zh: str
    kickoff_time: datetime
    match_num: str
    had: SportteryThreeWay | None
    hhad: SportteryHandicap | None
    source_url: str = PAGE_URL


async def fetch_sporttery_world_cup(client: httpx.AsyncClient) -> list[SportteryMatch]:
    headers = {
        "Referer": PAGE_URL,
        "Origin": "https://m.sporttery.cn",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    }
    last_status = 0
    for attempt in range(3):
        response = await client.get(
            API_URL,
            params={"channel": "c", "poolCode": "had,hhad"},
            headers=headers,
            timeout=settings.request_timeout_seconds,
        )
        last_status = response.status_code
        if response.status_code == 200:
            break
        logger.warning("体育彩票接口 HTTP {}，第 {} 次重试", response.status_code, attempt + 1)
        await asyncio.sleep(1.5 * (attempt + 1))
    else:
        logger.warning("体育彩票接口 HTTP {}：可能触发 WAF", last_status)
        return []

    payload = response.json()
    if not payload.get("success"):
        logger.warning("体育彩票接口返回失败：{}", payload.get("errorMessage"))
        return []

    matches: list[SportteryMatch] = []
    for match_day in payload.get("value", {}).get("matchInfoList", []):
        for match in match_day.get("subMatchList", []):
            league = str(match.get("leagueAllName") or match.get("leagueAbbName") or "")
            if "世界杯" not in league:
                continue
            parsed = _parse_match(match)
            if parsed:
                matches.append(parsed)
    return matches


def _parse_match(match: dict) -> SportteryMatch | None:
    kickoff = _parse_kickoff(match.get("matchDate"), match.get("matchTime"))
    if kickoff is None:
        return None

    had = _parse_had(match.get("had"))
    hhad = _parse_hhad(match.get("hhad"))
    if had is None and hhad is None:
        return None

    return SportteryMatch(
        match_id=str(match.get("matchId") or ""),
        home_team_zh=str(match.get("homeTeamAllName") or match.get("homeTeamAbbName") or ""),
        away_team_zh=str(match.get("awayTeamAllName") or match.get("awayTeamAbbName") or ""),
        kickoff_time=kickoff,
        match_num=str(match.get("matchNumStr") or ""),
        had=had,
        hhad=hhad,
    )


def _parse_had(raw: dict | None) -> SportteryThreeWay | None:
    if not isinstance(raw, dict) or not raw:
        return None
    home = _parse_odds(raw.get("h"))
    draw = _parse_odds(raw.get("d"))
    away = _parse_odds(raw.get("a"))
    if home is None or draw is None or away is None:
        return None
    return SportteryThreeWay(home=home, draw=draw, away=away)


def _parse_hhad(raw: dict | None) -> SportteryHandicap | None:
    if not isinstance(raw, dict) or not raw:
        return None
    home = _parse_odds(raw.get("h"))
    draw = _parse_odds(raw.get("d"))
    away = _parse_odds(raw.get("a"))
    goal_line = str(raw.get("goalLine") or raw.get("goalLineValue") or "").strip()
    if home is None or draw is None or away is None or not goal_line:
        return None
    return SportteryHandicap(
        goal_line=goal_line,
        label=format_handicap_label(goal_line),
        home=home,
        draw=draw,
        away=away,
    )


def format_handicap_label(goal_line: str) -> str:
    try:
        value = float(goal_line)
    except ValueError:
        return f"让球 {goal_line}"

    if value == 0:
        return "让球 0"
    if value < 0:
        n = abs(value)
        if n.is_integer():
            return f"主让{int(n)}球"
        return f"主让{abs(value)}球"
    if value.is_integer():
        return f"客让{int(value)}球"
    return f"客让{value}球"


def _parse_odds(value) -> float | None:
    try:
        odds = float(value)
    except (TypeError, ValueError):
        return None
    return odds if odds > 1 else None


def _parse_kickoff(match_date: str | None, match_time: str | None) -> datetime | None:
    if not match_date or not match_time:
        return None
    try:
        local_time = datetime.fromisoformat(f"{match_date}T{match_time}").replace(
            tzinfo=BEIJING_TZ
        )
    except ValueError:
        return None
    return local_time.astimezone(timezone.utc)
