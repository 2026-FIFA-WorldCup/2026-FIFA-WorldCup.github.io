from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from loguru import logger

from arbitrage.config import settings


API_URL = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry"
PAGE_URL = "https://m.sporttery.cn/mjc/jsq/zqspf/"
BEIJING_TZ = timezone(timedelta(hours=8))
CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "sporttery_cache.json"


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


async def fetch_sporttery_with_fallback(
    client: httpx.AsyncClient,
) -> tuple[list[SportteryMatch], bool]:
    live = await fetch_sporttery_world_cup(client)
    if live:
        save_sporttery_cache(live)
        return live, False

    cached = load_sporttery_cache()
    if cached:
        logger.info("体育彩票在线抓取失败，使用本地缓存 {} 场", len(cached))
        return cached, True
    return [], False


def save_sporttery_cache(matches: list[SportteryMatch]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "matches": [_serialize_match(match) for match in matches],
    }
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_sporttery_cache() -> list[SportteryMatch]:
    if not CACHE_PATH.exists():
        return []
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("读取体育彩票缓存失败：{}", exc)
        return []

    matches: list[SportteryMatch] = []
    for item in payload.get("matches", []):
        parsed = _deserialize_match(item)
        if parsed:
            matches.append(parsed)
    return matches


def _serialize_match(match: SportteryMatch) -> dict:
    return {
        "match_id": match.match_id,
        "home_team_zh": match.home_team_zh,
        "away_team_zh": match.away_team_zh,
        "kickoff_time": match.kickoff_time.isoformat(),
        "match_num": match.match_num,
        "source_url": match.source_url,
        "had": _serialize_three_way(match.had),
        "hhad": _serialize_handicap(match.hhad),
    }


def _serialize_three_way(value: SportteryThreeWay | None) -> dict | None:
    if value is None:
        return None
    return {"home": value.home, "draw": value.draw, "away": value.away}


def _serialize_handicap(value: SportteryHandicap | None) -> dict | None:
    if value is None:
        return None
    return {
        "goal_line": value.goal_line,
        "label": value.label,
        "home": value.home,
        "draw": value.draw,
        "away": value.away,
    }


def _deserialize_match(raw: dict) -> SportteryMatch | None:
    kickoff = parse_datetime(raw.get("kickoff_time"))
    if kickoff is None:
        return None
    had = _deserialize_three_way(raw.get("had"))
    hhad = _deserialize_handicap(raw.get("hhad"))
    if had is None and hhad is None:
        return None
    return SportteryMatch(
        match_id=str(raw.get("match_id") or ""),
        home_team_zh=str(raw.get("home_team_zh") or ""),
        away_team_zh=str(raw.get("away_team_zh") or ""),
        kickoff_time=kickoff,
        match_num=str(raw.get("match_num") or ""),
        had=had,
        hhad=hhad,
        source_url=str(raw.get("source_url") or PAGE_URL),
    )


def _deserialize_three_way(raw: dict | None) -> SportteryThreeWay | None:
    if not isinstance(raw, dict):
        return None
    home = _parse_odds(raw.get("home"))
    draw = _parse_odds(raw.get("draw"))
    away = _parse_odds(raw.get("away"))
    if home is None or draw is None or away is None:
        return None
    return SportteryThreeWay(home=home, draw=draw, away=away)


def _deserialize_handicap(raw: dict | None) -> SportteryHandicap | None:
    if not isinstance(raw, dict):
        return None
    goal_line = str(raw.get("goal_line") or "").strip()
    home = _parse_odds(raw.get("home"))
    draw = _parse_odds(raw.get("draw"))
    away = _parse_odds(raw.get("away"))
    if home is None or draw is None or away is None or not goal_line:
        return None
    label = str(raw.get("label") or format_handicap_label(goal_line))
    return SportteryHandicap(
        goal_line=goal_line,
        label=label,
        home=home,
        draw=draw,
        away=away,
    )


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


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
