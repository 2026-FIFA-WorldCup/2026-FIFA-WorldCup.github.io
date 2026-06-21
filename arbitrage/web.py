from __future__ import annotations

import asyncio
import html
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger

from arbitrage.config import settings
from arbitrage.core.handicap_from_scores import (
    aggregate_outcome_probs,
    parse_score_from_label,
    probs_to_odds,
)
from arbitrage.fetchers.polymarket import EVENTS_URL, PAGE_LIMIT, SOCCER_TAG_ID
from arbitrage.fetchers.sporttery_web import (
    SportteryHandicap,
    SportteryMatch,
    SportteryThreeWay,
    fetch_sporttery_world_cup,
    format_handicap_label,
)
from arbitrage.fetchers.utils import ensure_list, parse_datetime, parse_float, parse_matchup
from arbitrage.models import utc_now


REFRESH_SECONDS = int(os.getenv("WEB_REFRESH_SECONDS", "300"))
MAX_OFFSET = int(os.getenv("POLYMARKET_WEB_MAX_OFFSET", "400"))
WEB_WINDOW_DAYS = int(os.getenv("WEB_WINDOW_DAYS", "5"))
CONTACT_WECHAT = os.getenv("CONTACT_WECHAT", "wuke20010216")


TEAM_PROFILES: dict[str, tuple[str, str, str]] = {
    "Algeria": ("阿尔及利亚", "🇩🇿", "dz"),
    "Argentina": ("阿根廷", "🇦🇷", "ar"),
    "Australia": ("澳大利亚", "🇦🇺", "au"),
    "Austria": ("奥地利", "🇦🇹", "at"),
    "Belgium": ("比利时", "🇧🇪", "be"),
    "Bosnia-Herzegovina": ("波黑", "🇧🇦", "ba"),
    "Brazil": ("巴西", "🇧🇷", "br"),
    "Cabo Verde": ("佛得角", "🇨🇻", "cv"),
    "Canada": ("加拿大", "🇨🇦", "ca"),
    "Colombia": ("哥伦比亚", "🇨🇴", "co"),
    "Croatia": ("克罗地亚", "🇭🇷", "hr"),
    "Côte d'Ivoire": ("科特迪瓦", "🇨🇮", "ci"),
    "Curaçao": ("库拉索", "🇨🇼", "cw"),
    "Czechia": ("捷克", "🇨🇿", "cz"),
    "DR Congo": ("刚果（金）", "🇨🇩", "cd"),
    "Ecuador": ("厄瓜多尔", "🇪🇨", "ec"),
    "Egypt": ("埃及", "🇪🇬", "eg"),
    "England": ("英格兰", "🏴", "gb-eng"),
    "France": ("法国", "🇫🇷", "fr"),
    "Germany": ("德国", "🇩🇪", "de"),
    "Ghana": ("加纳", "🇬🇭", "gh"),
    "Haiti": ("海地", "🇭🇹", "ht"),
    "IR Iran": ("伊朗", "🇮🇷", "ir"),
    "Iraq": ("伊拉克", "🇮🇶", "iq"),
    "Japan": ("日本", "🇯🇵", "jp"),
    "Jordan": ("约旦", "🇯🇴", "jo"),
    "Korea Republic": ("韩国", "🇰🇷", "kr"),
    "Mexico": ("墨西哥", "🇲🇽", "mx"),
    "Morocco": ("摩洛哥", "🇲🇦", "ma"),
    "Netherlands": ("荷兰", "🇳🇱", "nl"),
    "New Zealand": ("新西兰", "🇳🇿", "nz"),
    "Norway": ("挪威", "🇳🇴", "no"),
    "Panama": ("巴拿马", "🇵🇦", "pa"),
    "Paraguay": ("巴拉圭", "🇵🇾", "py"),
    "Portugal": ("葡萄牙", "🇵🇹", "pt"),
    "Qatar": ("卡塔尔", "🇶🇦", "qa"),
    "Saudi Arabia": ("沙特阿拉伯", "🇸🇦", "sa"),
    "Scotland": ("苏格兰", "🏴", "gb-sct"),
    "Senegal": ("塞内加尔", "🇸🇳", "sn"),
    "South Africa": ("南非", "🇿🇦", "za"),
    "Spain": ("西班牙", "🇪🇸", "es"),
    "Sweden": ("瑞典", "🇸🇪", "se"),
    "Switzerland": ("瑞士", "🇨🇭", "ch"),
    "Tunisia": ("突尼斯", "🇹🇳", "tn"),
    "Türkiye": ("土耳其", "🇹🇷", "tr"),
    "United States": ("美国", "🇺🇸", "us"),
    "Uruguay": ("乌拉圭", "🇺🇾", "uy"),
    "Uzbekistan": ("乌兹别克斯坦", "🇺🇿", "uz"),
}

FLAG_CDN = os.getenv("FLAG_CDN_BASE", "https://flagcdn.com/w80")


app = FastAPI(title="Polymarket 足球赔率")


@dataclass
class MarketOption:
    label: str
    probability: float
    odds: float
    url: str


@dataclass
class MarketGroup:
    name: str
    options: list[MarketOption] = field(default_factory=list)


@dataclass
class ComparisonRow:
    outcome: str
    sporttery_odds: float | None
    sporttery_prob: float | None
    polymarket_odds: float | None
    polymarket_prob: float | None


@dataclass
class OddsComparison:
    title: str
    note: str
    rows: list[ComparisonRow] = field(default_factory=list)


@dataclass
class MatchView:
    title: str
    home_team: str
    away_team: str
    kickoff_time: datetime
    url: str
    sporttery: SportteryMatch | None = None
    comparisons: list[OddsComparison] = field(default_factory=list)
    markets: list[MarketGroup] = field(default_factory=list)


cache: dict[str, Any] = {
    "updated_at": None,
    "matches": [],
    "error": None,
    "refresh_seconds": REFRESH_SECONDS,
}


@app.on_event("startup")
async def startup() -> None:
    await refresh_cache()
    asyncio.create_task(refresh_loop())


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(render_html(cache))


@app.get("/api/odds")
async def api_odds() -> JSONResponse:
    return JSONResponse(
        {
            "updated_at": cache["updated_at"],
            "error": cache["error"],
            "refresh_seconds": cache["refresh_seconds"],
            "matches": [_match_to_dict(match) for match in cache["matches"]],
        }
    )


@app.post("/api/refresh")
async def api_refresh() -> JSONResponse:
    await refresh_cache()
    return JSONResponse(
        {
            "ok": not cache["matches"] or cache["error"] is None,
            "updated_at": cache["updated_at"],
            "error": cache["error"],
            "match_count": len(cache["matches"]),
        }
    )


async def refresh_loop() -> None:
    while True:
        await asyncio.sleep(REFRESH_SECONDS)
        await refresh_cache()


async def refresh_cache() -> None:
    errors: list[str] = []
    try:
        client_kwargs: dict = {
            "headers": {"User-Agent": "football-odds-web/0.1"},
            "timeout": settings.request_timeout_seconds,
        }
        poly_kwargs = dict(client_kwargs)
        if settings.http_proxy:
            poly_kwargs["proxy"] = settings.http_proxy

        async with httpx.AsyncClient(**client_kwargs) as domestic_client:
            async with httpx.AsyncClient(**poly_kwargs) as poly_client:
                poly_result, sporttery_result = await asyncio.gather(
                    fetch_polymarket_match_views(poly_client),
                    fetch_sporttery_world_cup(domestic_client),
                    return_exceptions=True,
                )

        if isinstance(poly_result, Exception):
            poly_matches: list[MatchView] = []
            errors.append(f"Polymarket: {poly_result.__class__.__name__}")
            logger.warning("Polymarket 抓取失败：{}", poly_result)
        else:
            poly_matches = poly_result

        if isinstance(sporttery_result, Exception):
            sporttery_matches: list[SportteryMatch] = []
            errors.append(f"体育彩票: {sporttery_result.__class__.__name__}")
            logger.warning("体育彩票抓取失败：{}", sporttery_result)
        else:
            sporttery_matches = sporttery_result

        if not poly_matches and not sporttery_matches:
            cache["error"] = "; ".join(errors) or "暂无可用数据"
            logger.warning("Web 缓存刷新失败：{}", cache["error"])
            return

        if not poly_matches and sporttery_matches:
            poly_matches = _sporttery_only_match_views(sporttery_matches)

        matches = _attach_sporttery_and_comparisons(poly_matches, sporttery_matches)
        cache["matches"] = matches
        cache["updated_at"] = utc_now().isoformat()
        cache["error"] = "; ".join(errors) if errors else None
        logger.info(
            "Web 缓存刷新完成：Polymarket {} 场，体育彩票 {} 场，已匹配 {} 场",
            len(poly_matches),
            len(sporttery_matches),
            sum(1 for match in matches if match.sporttery),
        )
    except Exception as exc:
        cache["error"] = str(exc) or exc.__class__.__name__
        logger.warning("Web 缓存刷新失败：{}", cache["error"])


async def fetch_polymarket_match_views(client: httpx.AsyncClient) -> list[MatchView]:
    events = await _fetch_soccer_events(client)
    grouped: dict[str, MatchView] = {}
    now = utc_now()
    max_kickoff = now + timedelta(days=WEB_WINDOW_DAYS)

    for event in events:
        if not _is_world_cup_match_event(event):
            continue
        title = str(event.get("title") or "").strip()
        base_title, market_name = _split_event_title(title)
        matchup = parse_matchup(base_title)
        if not matchup:
            continue

        kickoff = parse_datetime(event.get("endDate") or event.get("end_date"))
        if kickoff is None or not (now <= kickoff <= max_kickoff):
            continue

        key = _match_key(base_title, kickoff)
        event_url = f"https://polymarket.com/event/{event.get('slug')}"
        if key not in grouped:
            home_team, away_team = matchup
            grouped[key] = MatchView(
                title=base_title,
                home_team=home_team,
                away_team=away_team,
                kickoff_time=kickoff,
                url=event_url,
            )

        options = _parse_market_options(event.get("markets") or [], event_url)
        if options:
            grouped[key].markets.append(MarketGroup(name=market_name, options=options))

    return sorted(grouped.values(), key=lambda match: match.kickoff_time)


async def _fetch_soccer_events(client: httpx.AsyncClient) -> list[dict]:
    events: list[dict] = []
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
        )
        response.raise_for_status()
        payload = response.json()
        page_events = payload.get("data") if isinstance(payload, dict) else payload
        if not page_events:
            break
        events.extend(page_events)
    return events


def _split_event_title(title: str) -> tuple[str, str]:
    if " - " not in title:
        return title, "胜平负"

    base_title, suffix = title.split(" - ", 1)
    suffix_map = {
        "Halftime Result": "半场结果",
        "Exact Score": "精确比分",
        "More Markets": "更多市场",
    }
    return base_title.strip(), suffix_map.get(suffix.strip(), suffix.strip())


def _parse_market_options(markets: list[dict], event_url: str) -> list[MarketOption]:
    options: list[MarketOption] = []
    for market in markets:
        if market.get("closed") or not market.get("active", True):
            continue
        probability = _yes_probability(market)
        if probability is None:
            continue
        label = _option_label(market)
        options.append(
            MarketOption(
                label=label,
                probability=probability,
                odds=1 / probability,
                url=event_url,
            )
        )
    return sorted(options, key=lambda option: option.probability, reverse=True)


def _yes_probability(market: dict) -> float | None:
    outcomes = [str(item).casefold() for item in ensure_list(market.get("outcomes"))]
    prices = [parse_float(item) for item in ensure_list(market.get("outcomePrices"))]
    if len(outcomes) != len(prices):
        return None
    for outcome, price in zip(outcomes, prices):
        if outcome == "yes" and price is not None and 0 < price < 1:
            return price
    return None


def _option_label(market: dict) -> str:
    label = str(market.get("groupItemTitle") or "").strip()
    if not label:
        label = str(market.get("question") or "").strip()
    return _translate_label(label)


def _translate_label(label: str) -> str:
    translated = label
    for english_name in sorted(TEAM_PROFILES, key=len, reverse=True):
        translated = translated.replace(english_name, team_name_zh(english_name))

    replacements = {
        "Draw": "平局",
        "draw": "平局",
        "Yes": "是",
        "No": "否",
        "Both teams to score": "双方都有进球",
        "Over": "大于",
        "Under": "小于",
        "goals": "球",
        "goal": "球",
    }
    for source, target in replacements.items():
        translated = translated.replace(source, target)
    if translated.casefold().startswith("draw"):
        return "平局"
    return translated


def _is_world_cup_match_event(event: dict) -> bool:
    slug = str(event.get("slug") or "").casefold()
    title = str(event.get("title") or "").casefold()
    return slug.startswith("fifwc-") and " vs" in title


def _match_key(base_title: str, kickoff: datetime) -> str:
    return f"{base_title.casefold()}|{kickoff.isoformat()}"


def _sporttery_only_match_views(sporttery_matches: list[SportteryMatch]) -> list[MatchView]:
    now = utc_now()
    max_kickoff = now + timedelta(days=WEB_WINDOW_DAYS)
    views: list[MatchView] = []
    for match in sporttery_matches:
        if not (now <= match.kickoff_time <= max_kickoff):
            continue
        home_en = cn_team_to_en(match.home_team_zh)
        away_en = cn_team_to_en(match.away_team_zh)
        views.append(
            MatchView(
                title=f"{home_en} vs {away_en}",
                home_team=home_en,
                away_team=away_en,
                kickoff_time=match.kickoff_time,
                url=match.source_url,
                sporttery=match,
            )
        )
    return sorted(views, key=lambda item: item.kickoff_time)


def _attach_sporttery_and_comparisons(
    poly_matches: list[MatchView], sporttery_matches: list[SportteryMatch]
) -> list[MatchView]:
    now = utc_now()
    max_kickoff = now + timedelta(days=WEB_WINDOW_DAYS)
    sporttery_in_window = [
        match for match in sporttery_matches if now <= match.kickoff_time <= max_kickoff
    ]

    for poly in poly_matches:
        if poly.sporttery is None:
            sporttery = _find_sporttery_match(poly, sporttery_in_window)
            poly.sporttery = sporttery
        if poly.sporttery:
            poly.comparisons = _build_comparisons(poly, poly.sporttery)
    return poly_matches


def _find_sporttery_match(
    poly: MatchView, sporttery_matches: list[SportteryMatch]
) -> SportteryMatch | None:
    for candidate in sporttery_matches:
        home_en = cn_team_to_en(candidate.home_team_zh)
        away_en = cn_team_to_en(candidate.away_team_zh)
        if home_en != poly.home_team or away_en != poly.away_team:
            continue
        if abs((candidate.kickoff_time - poly.kickoff_time).total_seconds()) > 3600:
            continue
        return candidate
    return None


def _build_comparisons(poly: MatchView, sporttery: SportteryMatch) -> list[OddsComparison]:
    comparisons: list[OddsComparison] = []
    poly_1x2 = _extract_polymarket_three_way(poly)

    if sporttery.had:
        poly_had = poly_1x2 or _outcome_map_from_scores(poly, goal_line=None)
        if poly_had:
            comparisons.append(
                _build_three_way_comparison(
                    title="胜平负对比",
                    note=(
                        "体育彩票为官方固定欧赔；Polymarket 由精确比分概率汇总后换算，"
                        "不含「其他比分」选项。"
                    ),
                    sporttery=sporttery.had,
                    polymarket=poly_had,
                )
            )

    if sporttery.hhad:
        poly_handicap = _calc_handicap_from_exact_scores(poly, sporttery.hhad)
        note = (
            f"体育彩票盘口：{sporttery.hhad.label}（goalLine={sporttery.hhad.goal_line}）。"
            "Polymarket 侧根据精确比分概率，按让球规则汇总主胜/平/客胜后换算欧赔。"
            "结算：调整后主队进球 = 实际主队进球 + 让球数，再与客队比较。"
        )
        if not poly_handicap:
            note += " 当前无可用精确比分数据，仅展示体育彩票让球赔率。"
        comparisons.append(
            _build_handicap_comparison(
                title=f"让球对比 · {sporttery.hhad.label}",
                note=note,
                sporttery=sporttery.hhad,
                polymarket=poly_handicap,
            )
        )
    return comparisons


def _build_three_way_comparison(
    title: str,
    note: str,
    sporttery: SportteryThreeWay,
    polymarket: dict[str, MarketOption],
) -> OddsComparison:
    rows = [
        _comparison_row("主胜", sporttery.home, polymarket.get("home")),
        _comparison_row("平局", sporttery.draw, polymarket.get("draw")),
        _comparison_row("客胜", sporttery.away, polymarket.get("away")),
    ]
    return OddsComparison(title=title, note=note, rows=rows)


def _build_handicap_comparison(
    title: str,
    note: str,
    sporttery: SportteryHandicap,
    polymarket: dict[str, MarketOption] | None,
) -> OddsComparison:
    rows = [
        _comparison_row(
            "主胜",
            sporttery.home,
            polymarket.get("home") if polymarket else None,
        ),
        _comparison_row(
            "平局",
            sporttery.draw,
            polymarket.get("draw") if polymarket else None,
        ),
        _comparison_row(
            "客胜",
            sporttery.away,
            polymarket.get("away") if polymarket else None,
        ),
    ]
    return OddsComparison(title=title, note=note, rows=rows)


def _comparison_row_from_map(
    outcome: str,
    sporttery_odds: float | None,
    polymarket: dict[str, MarketOption] | None,
    key: str,
) -> ComparisonRow:
    poly_opt = polymarket.get(key) if polymarket else None
    return ComparisonRow(
        outcome=outcome,
        sporttery_odds=sporttery_odds,
        sporttery_prob=_implied_prob(sporttery_odds),
        polymarket_odds=poly_opt.odds if poly_opt else None,
        polymarket_prob=poly_opt.probability if poly_opt else None,
    )


def _extract_score_lines(poly: MatchView) -> list[tuple[int, int, float]]:
    market = _get_market_by_name(poly, "精确比分")
    if not market:
        return []

    scores: list[tuple[int, int, float]] = []
    for option in market.options:
        parsed = parse_score_from_label(option.label)
        if parsed is None:
            continue
        scores.append((parsed.home_goals, parsed.away_goals, option.probability))
    return scores


def _outcome_map_from_scores(
    poly: MatchView, goal_line: float | None
) -> dict[str, MarketOption]:
    scores = _extract_score_lines(poly)
    if not scores:
        return {}

    probs = aggregate_outcome_probs(scores, goal_line=goal_line)
    if not probs:
        return {}

    odds_map = probs_to_odds(probs)
    return {
        key: MarketOption(
            label=key,
            probability=probs[key],
            odds=odds_map[key],
            url=poly.url,
        )
        for key in ("home", "draw", "away")
        if key in probs and probs[key] > 0
    }


def _calc_handicap_from_exact_scores(
    poly: MatchView, sporttery_hhad: SportteryHandicap
) -> dict[str, MarketOption] | None:
    goal_line = _parse_goal_line(sporttery_hhad.goal_line)
    if goal_line is None:
        return None

    result = _outcome_map_from_scores(poly, goal_line=goal_line)
    if result:
        return result

    return _extract_polymarket_handicap(poly, sporttery_hhad)


def _comparison_row(
    outcome: str, sporttery_odds: float, polymarket_option: MarketOption | None
) -> ComparisonRow:
    return ComparisonRow(
        outcome=outcome,
        sporttery_odds=sporttery_odds,
        sporttery_prob=_implied_prob(sporttery_odds),
        polymarket_odds=polymarket_option.odds if polymarket_option else None,
        polymarket_prob=polymarket_option.probability if polymarket_option else None,
    )


def _implied_prob(odds: float | None) -> float | None:
    if odds is None or odds <= 0:
        return None
    return 1.0 / odds


def _extract_polymarket_three_way(poly: MatchView) -> dict[str, MarketOption]:
    market = _get_market_by_name(poly, "胜平负")
    if not market:
        return {}

    result: dict[str, MarketOption] = {}
    home_zh = team_name_zh(poly.home_team)
    away_zh = team_name_zh(poly.away_team)
    for option in market.options:
        label = option.label.casefold()
        if "平局" in option.label or label == "draw":
            result["draw"] = option
        elif poly.home_team.casefold() in label or home_zh in option.label:
            result["home"] = option
        elif poly.away_team.casefold() in label or away_zh in option.label:
            result["away"] = option
    return result


def _extract_polymarket_handicap(
    poly: MatchView, sporttery_hhad: SportteryHandicap
) -> dict[str, MarketOption] | None:
    target_line = _parse_goal_line(sporttery_hhad.goal_line)
    if target_line is None:
        return None

    more_market = _get_market_by_name(poly, "更多市场")
    if not more_market:
        return None

    parsed: dict[str, MarketOption] = {}
    for option in more_market.options:
        mapped = _map_handicap_option(option, poly, target_line)
        if mapped:
            parsed[mapped] = option
    return parsed or None


def _map_handicap_option(
    option: MarketOption, poly: MatchView, target_line: float
) -> str | None:
    text = option.label
    line = _extract_line_from_text(text)
    if line is None or abs(line - target_line) > 0.01:
        return None

    lower = text.casefold()
    if "平局" in text or "draw" in lower:
        return "draw"
    if poly.home_team.casefold() in lower or team_name_zh(poly.home_team) in text:
        return "home"
    if poly.away_team.casefold() in lower or team_name_zh(poly.away_team) in text:
        return "away"
    if "win by" in lower or "净胜" in text or "beat" in lower:
        return "home"
    return None


def _extract_line_from_text(text: str) -> float | None:
    match = re.search(r"\(([+-]?\d+(?:\.\d+)?)\)", text)
    if match:
        return float(match.group(1))
    match = re.search(r"([+-]\d+(?:\.\d+)?)\s*球", text)
    if match:
        return float(match.group(1))
    match = re.search(r"win by (\d+)", text, flags=re.IGNORECASE)
    if match:
        return -float(match.group(1))
    return None


def _parse_goal_line(goal_line: str) -> float | None:
    try:
        return float(goal_line)
    except ValueError:
        return None


def _get_market_by_name(poly: MatchView, name: str) -> MarketGroup | None:
    for market in poly.markets:
        if market.name == name:
            return market
    return None


def _load_cn_team_map() -> dict[str, str]:
    aliases_path = Path(__file__).resolve().parent / "team_aliases.json"
    mapping: dict[str, str] = {}
    if not aliases_path.exists():
        return mapping

    aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
    for alias_list in aliases.values():
        english = next((alias for alias in alias_list if alias in TEAM_PROFILES), None)
        if english is None:
            english = next((alias for alias in alias_list if alias.isascii()), None)
        if english is None:
            continue
        for alias in alias_list:
            if any("\u4e00" <= char <= "\u9fff" for char in alias):
                mapping[alias] = english
    mapping["沙特"] = "Saudi Arabia"
    mapping["刚果(金)"] = "DR Congo"
    return mapping


CN_TEAM_TO_EN = _load_cn_team_map()


def cn_team_to_en(name_zh: str) -> str:
    cleaned = name_zh.strip()
    if cleaned in CN_TEAM_TO_EN:
        return CN_TEAM_TO_EN[cleaned]
    for key, value in CN_TEAM_TO_EN.items():
        if key in cleaned or cleaned in key:
            return value
    return cleaned


def _match_to_dict(match: MatchView) -> dict[str, Any]:
    return {
        "title": match.title,
        "home_team": match.home_team,
        "away_team": match.away_team,
        "home_team_zh": team_name_zh(match.home_team),
        "away_team_zh": team_name_zh(match.away_team),
        "home_flag": team_flag(match.home_team),
        "away_flag": team_flag(match.away_team),
        "kickoff_time": match.kickoff_time.isoformat(),
        "url": match.url,
        "sporttery": {
            "match_num": match.sporttery.match_num,
            "source_url": match.sporttery.source_url,
            "had": _three_way_to_dict(match.sporttery.had),
            "hhad": _handicap_to_dict(match.sporttery.hhad),
        }
        if match.sporttery
        else None,
        "comparisons": [
            {
                "title": comparison.title,
                "note": comparison.note,
                "rows": [
                    {
                        "outcome": row.outcome,
                        "sporttery_odds": row.sporttery_odds,
                        "sporttery_prob": row.sporttery_prob,
                        "polymarket_odds": row.polymarket_odds,
                        "polymarket_prob": row.polymarket_prob,
                    }
                    for row in comparison.rows
                ],
            }
            for comparison in match.comparisons
        ],
        "markets": [
            {
                "name": market.name,
                "options": [
                    {
                        "label": option.label,
                        "probability": option.probability,
                        "odds": option.odds,
                        "url": option.url,
                    }
                    for option in market.options
                ],
            }
            for market in match.markets
        ],
    }


def _three_way_to_dict(value: SportteryThreeWay | None) -> dict[str, float] | None:
    if value is None:
        return None
    return {"home": value.home, "draw": value.draw, "away": value.away}


def _handicap_to_dict(value: SportteryHandicap | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "goal_line": value.goal_line,
        "label": value.label,
        "home": value.home,
        "draw": value.draw,
        "away": value.away,
    }


def render_html(state: dict[str, Any]) -> str:
    matches: list[MatchView] = state["matches"]
    updated_at = state["updated_at"] or "尚未成功刷新"
    error = state["error"]
    static_site = os.getenv("STATIC_SITE", "").lower() in ("1", "true", "yes")
    cards = "\n".join(render_match_card(match, index) for index, match in enumerate(matches))
    if not cards:
        cards = '<div class="empty-state"><p>未来 5 天暂无可展示的世界杯比赛。</p><p class="hint">请稍后点击「立即刷新」重试，或检查网络连接。</p></div>'

    error_html = (
        f'<div class="alert alert-warn">{html.escape(error)}</div>' if error else ""
    )
    refresh_script = (
        "btn.addEventListener(\"click\", () => location.reload());"
        if static_site
        else """btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "刷新中…";
      try {
        const res = await fetch("/api/refresh", { method: "POST" });
        if (res.ok) location.reload();
        else btn.textContent = "刷新失败";
      } catch {
        btn.textContent = "刷新失败";
      } finally {
        btn.disabled = false;
      }
    });"""
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>世界杯赔率对比 · 体育彩票 × Polymarket</title>
  <style>
    :root {{
      --bg: #f4f6f9;
      --surface: #ffffff;
      --border: #e3e8ef;
      --border-strong: #cfd6e0;
      --text: #1a2332;
      --muted: #64748b;
      --primary: #2563eb;
      --primary-soft: #eff6ff;
      --lottery: #c2410c;
      --lottery-soft: #fff7ed;
      --poly: #047857;
      --poly-soft: #ecfdf5;
      --better: #15803d;
      --warn-bg: #fef3c7;
      --warn-text: #92400e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
        "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    .topbar {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 20px clamp(16px, 4vw, 48px);
    }}
    .topbar-inner {{
      max-width: 1080px;
      margin: 0 auto;
    }}
    .brand {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(22px, 3vw, 28px);
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .subtitle {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin-top: 16px;
    }}
    .meta-tag {{
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 6px;
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--muted);
      font-size: 12px;
    }}
    .btn {{
      appearance: none;
      border: 1px solid var(--primary);
      background: var(--primary);
      color: #fff;
      border-radius: 8px;
      padding: 8px 16px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }}
    .btn:hover {{ background: #1d4ed8; }}
    .btn:disabled {{ opacity: .6; cursor: wait; }}
    main {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 24px clamp(16px, 4vw, 48px) 64px;
    }}
    .alert {{
      padding: 12px 14px;
      border-radius: 8px;
      margin-bottom: 16px;
      font-size: 13px;
    }}
    .alert-warn {{
      background: var(--warn-bg);
      color: var(--warn-text);
      border: 1px solid #fcd34d;
    }}
    .match-list {{
      display: flex;
      flex-direction: column;
      gap: 14px;
    }}
    .match-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(15, 23, 42, .06);
    }}
    .match-head {{
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      gap: 12px;
      padding: 18px 20px 12px;
      border-bottom: 1px solid var(--border);
    }}
    .team-block {{ min-width: 0; }}
    .team-block.away {{ text-align: right; }}
    .team-flag-wrap {{ margin-bottom: 6px; min-height: 32px; }}
      display: inline-block;
      width: 44px;
      height: 32px;
      object-fit: cover;
      border-radius: 4px;
      border: 1px solid var(--border);
      background: #fff;
      box-shadow: 0 1px 2px rgba(15, 23, 42, .08);
    }}
    .team-name {{
      font-size: 18px;
      font-weight: 700;
      color: var(--text);
    }}
    .team-en {{
      font-size: 12px;
      color: var(--muted);
      margin-top: 2px;
    }}
    .match-meta {{
      text-align: center;
      min-width: 88px;
    }}
    .match-meta .vs {{
      font-size: 13px;
      font-weight: 700;
      color: var(--muted);
    }}
    .match-meta .time {{
      margin-top: 4px;
      font-size: 12px;
      color: var(--muted);
      white-space: nowrap;
    }}
    .match-meta .league {{
      font-size: 11px;
      color: var(--primary);
      font-weight: 600;
      margin-bottom: 4px;
    }}
    .odds-section {{
      padding: 16px 20px 18px;
    }}
    .odds-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }}
    .odds-title h2 {{
      margin: 0;
      font-size: 14px;
      font-weight: 600;
      color: var(--text);
    }}
    .odds-links {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .link-chip {{
      font-size: 12px;
      color: var(--primary);
      text-decoration: none;
      padding: 3px 8px;
      border-radius: 6px;
      background: var(--primary-soft);
      border: 1px solid #bfdbfe;
    }}
    .link-chip:hover {{ background: #dbeafe; }}
    .odds-grid {{
      display: grid;
      grid-template-columns: 88px repeat(3, 1fr);
      gap: 1px;
      background: var(--border);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
    }}
    .odds-cell {{
      background: var(--surface);
      padding: 10px 12px;
      font-size: 13px;
    }}
    .odds-cell.head {{
      background: #f8fafc;
      color: var(--muted);
      font-weight: 600;
      font-size: 12px;
    }}
    .odds-cell.label {{
      background: #f8fafc;
      color: var(--muted);
      font-weight: 600;
      font-size: 12px;
    }}
    .odds-cell.lottery {{ background: var(--lottery-soft); }}
    .odds-cell.poly {{ background: var(--poly-soft); }}
    .odds-cell.outcome {{
      text-align: center;
      font-weight: 600;
    }}
    .odds-value {{
      display: block;
      font-size: 18px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      color: var(--text);
    }}
    .odds-cell.lottery .odds-value {{ color: var(--lottery); }}
    .odds-cell.poly .odds-value {{ color: var(--poly); }}
    .odds-sub {{
      display: block;
      margin-top: 2px;
      font-size: 11px;
      color: var(--muted);
    }}
    .odds-cell.better .odds-value {{
      color: var(--better);
      text-decoration: underline;
      text-underline-offset: 2px;
    }}
    .details-toggle {{
      border-top: 1px solid var(--border);
    }}
    .details-toggle summary {{
      list-style: none;
      cursor: pointer;
      padding: 12px 20px;
      font-size: 13px;
      font-weight: 600;
      color: var(--primary);
      background: #fafbfc;
      user-select: none;
    }}
    .details-toggle summary::-webkit-details-marker {{ display: none; }}
    .details-toggle summary::after {{
      content: " ▾";
      font-size: 12px;
    }}
    .details-toggle[open] summary::after {{ content: " ▴"; }}
    .details-body {{
      padding: 0 20px 18px;
    }}
    .detail-block {{
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px dashed var(--border);
    }}
    .detail-block:first-child {{
      margin-top: 0;
      padding-top: 4px;
      border-top: 0;
    }}
    .detail-block h3 {{
      margin: 0 0 8px;
      font-size: 13px;
      font-weight: 600;
      color: var(--text);
    }}
    .detail-note {{
      margin: 0 0 10px;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.6;
    }}
    .data-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    .data-table th,
    .data-table td {{
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      text-align: left;
    }}
    .data-table th {{
      background: #f8fafc;
      color: var(--muted);
      font-weight: 600;
      font-size: 12px;
    }}
    .data-table td.num {{
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}
    .data-table tr:last-child td {{ border-bottom: 0; }}
    .empty-state {{
      text-align: center;
      padding: 48px 24px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      color: var(--muted);
    }}
    .empty-state p {{ margin: 0 0 8px; }}
    .hint {{ font-size: 13px; }}
    .card-footer {{
      padding: 14px 20px 18px;
      border-top: 1px solid var(--border);
      background: #fafbfc;
      text-align: center;
    }}
    .btn-contact {{
      appearance: none;
      border: 1px solid var(--primary);
      background: var(--surface);
      color: var(--primary);
      border-radius: 8px;
      padding: 9px 28px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: background .15s, color .15s;
    }}
    .btn-contact:hover {{
      background: var(--primary);
      color: #fff;
    }}
    .modal-overlay {{
      display: none;
      position: fixed;
      inset: 0;
      z-index: 1000;
      background: rgba(15, 23, 42, .45);
      align-items: center;
      justify-content: center;
      padding: 20px;
    }}
    .modal-overlay.open {{ display: flex; }}
    .modal-box {{
      background: var(--surface);
      border-radius: 12px;
      padding: 28px 32px;
      max-width: 360px;
      width: 100%;
      text-align: center;
      box-shadow: 0 20px 50px rgba(15, 23, 42, .18);
      border: 1px solid var(--border);
    }}
    .modal-box h3 {{
      margin: 0 0 12px;
      font-size: 18px;
      color: var(--text);
    }}
    .modal-wechat {{
      margin: 0 0 20px;
      font-size: 16px;
      color: var(--primary);
      font-weight: 700;
      letter-spacing: .02em;
    }}
    .modal-close {{
      appearance: none;
      border: 1px solid var(--border);
      background: var(--bg);
      color: var(--muted);
      border-radius: 8px;
      padding: 8px 24px;
      font-size: 13px;
      cursor: pointer;
    }}
    .modal-close:hover {{ background: var(--border); }}
    @media (max-width: 640px) {{
      .match-head {{
        grid-template-columns: 1fr;
        text-align: center;
      }}
      .team-block.away {{ text-align: center; }}
      .odds-grid {{
        grid-template-columns: 72px repeat(3, 1fr);
      }}
      .odds-value {{ font-size: 16px; }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <div>
          <h1>世界杯赔率对比</h1>
          <p class="subtitle">未来 {WEB_WINDOW_DAYS} 天 · 体育彩票 vs Polymarket 胜平负实时对比</p>
        </div>
        <button class="btn" id="refresh-btn" type="button">立即刷新</button>
      </div>
      <div class="toolbar">
        <span class="meta-tag">共 {len(matches)} 场</span>
        <span class="meta-tag">每 {REFRESH_SECONDS // 60} 分钟自动更新</span>
        <span class="meta-tag" id="updated-at">更新：{html.escape(str(updated_at))}</span>
      </div>
    </div>
  </header>
  <main>
    {error_html}
    <div class="match-list">{cards}</div>
  </main>
  <div class="modal-overlay" id="contact-modal" role="dialog" aria-modal="true" aria-labelledby="contact-modal-title">
    <div class="modal-box">
      <h3 id="contact-modal-title">联系购买</h3>
      <p class="modal-wechat">请联系微信 {html.escape(CONTACT_WECHAT)}</p>
      <button class="modal-close" type="button" id="contact-modal-close">关闭</button>
    </div>
  </div>
  <script>
    const REFRESH_MS = {REFRESH_SECONDS * 1000};
    const btn = document.getElementById("refresh-btn");
    {refresh_script}
    setTimeout(() => location.reload(), REFRESH_MS);

    const modal = document.getElementById("contact-modal");
    const modalClose = document.getElementById("contact-modal-close");
    document.querySelectorAll(".btn-contact").forEach((el) => {{
      el.addEventListener("click", () => modal.classList.add("open"));
    }});
    modalClose.addEventListener("click", () => modal.classList.remove("open"));
    modal.addEventListener("click", (e) => {{
      if (e.target === modal) modal.classList.remove("open");
    }});
    document.addEventListener("keydown", (e) => {{
      if (e.key === "Escape") modal.classList.remove("open");
    }});
  </script>
</body>
</html>"""


def render_match_card(match: MatchView, index: int) -> str:
    kickoff = match.kickoff_time.strftime("%m-%d %H:%M UTC")
    home_zh = team_name_zh(match.home_team)
    away_zh = team_name_zh(match.away_team)
    primary_title = _primary_section_title(match)
    main_odds = render_main_odds_grid(match)
    details = render_match_details(match, index)
    links = [
        f'<a class="link-chip" href="{html.escape(match.url)}" target="_blank" rel="noopener">Polymarket</a>'
    ]
    if match.sporttery:
        links.append(
            f'<a class="link-chip" href="{html.escape(match.sporttery.source_url)}" '
            f'target="_blank" rel="noopener">体育彩票 · {html.escape(match.sporttery.match_num)}</a>'
        )
    links_html = "\n".join(links)
    return f"""
<article class="match-card">
  <div class="match-head">
    <div class="team-block">
      <div class="team-flag-wrap">{render_team_flag(match.home_team)}</div>
      <div class="team-name">{html.escape(home_zh)}</div>
      <div class="team-en">{html.escape(match.home_team)}</div>
    </div>
    <div class="match-meta">
      <div class="league">FIFA 世界杯</div>
      <div class="vs">VS</div>
      <div class="time">{kickoff}</div>
    </div>
    <div class="team-block away">
      <div class="team-flag-wrap">{render_team_flag(match.away_team)}</div>
      <div class="team-name">{html.escape(away_zh)}</div>
      <div class="team-en">{html.escape(match.away_team)}</div>
    </div>
  </div>
  <div class="odds-section">
    <div class="odds-title">
      <h2>{html.escape(primary_title)}</h2>
      <div class="odds-links">{links_html}</div>
    </div>
    {main_odds}
  </div>
  {details}
  <div class="card-footer">
    <button class="btn-contact" type="button">联系购买</button>
  </div>
</article>"""


def _primary_comparison(match: MatchView) -> OddsComparison | None:
    if match.sporttery and match.sporttery.hhad:
        for comparison in match.comparisons:
            if comparison.title.startswith("让球对比"):
                return comparison
    for comparison in match.comparisons:
        if comparison.title == "胜平负对比":
            return comparison
    return match.comparisons[0] if match.comparisons else None


def _primary_section_title(match: MatchView) -> str:
    comparison = _primary_comparison(match)
    if comparison and comparison.title.startswith("让球对比"):
        return f"体育彩票 {comparison.title.replace('让球对比 · ', '')} · 赔率对比"
    if match.sporttery and match.sporttery.hhad and not match.sporttery.had:
        return f"体育彩票 {match.sporttery.hhad.label} · 赔率对比"
    return "胜平负 · 赔率对比"


def render_main_odds_grid(match: MatchView) -> str:
    comparison = _primary_comparison(match)
    outcomes = [
        ("主胜", "home"),
        ("平局", "draw"),
        ("客胜", "away"),
    ]

    if comparison:
        row_map = {row.outcome: row for row in comparison.rows}
    else:
        row_map = _fallback_main_rows(match, outcomes)

    header_cells = "".join(
        f'<div class="odds-cell head outcome">{html.escape(label)}</div>'
        for label, _ in outcomes
    )
    lottery_cells = "".join(
        render_odds_grid_cell(row_map.get(label), side="lottery") for label, _ in outcomes
    )
    poly_cells = "".join(
        render_odds_grid_cell(row_map.get(label), side="poly") for label, _ in outcomes
    )

    return f"""
<div class="odds-grid">
  <div class="odds-cell label"></div>
  {header_cells}
  <div class="odds-cell label">体育彩票</div>
  {lottery_cells}
  <div class="odds-cell label">Polymarket</div>
  {poly_cells}
</div>"""


def _fallback_main_rows(
    match: MatchView, outcomes: list[tuple[str, str]]
) -> dict[str, ComparisonRow]:
    row_map: dict[str, ComparisonRow] = {}
    sporttery = match.sporttery
    if sporttery and sporttery.hhad:
        poly_map = _calc_handicap_from_exact_scores(match, sporttery.hhad) or {}
        source = sporttery.hhad
    elif sporttery and sporttery.had:
        poly_map = _extract_polymarket_three_way(match) or _outcome_map_from_scores(
            match, goal_line=None
        )
        source = sporttery.had
    else:
        poly_map = _extract_polymarket_three_way(match)
        source = None

    for label, key in outcomes:
        lottery_odds = getattr(source, key, None) if source else None
        poly_opt = poly_map.get(key) if isinstance(poly_map, dict) else None
        row_map[label] = ComparisonRow(
            outcome=label,
            sporttery_odds=lottery_odds,
            sporttery_prob=_implied_prob(lottery_odds),
            polymarket_odds=poly_opt.odds if poly_opt else None,
            polymarket_prob=poly_opt.probability if poly_opt else None,
        )
    return row_map


def render_odds_grid_cell(row: ComparisonRow | None, side: str) -> str:
    if row is None:
        return f'<div class="odds-cell {side}"><span class="odds-value">—</span></div>'

    if side == "lottery":
        odds = row.sporttery_odds
        prob = row.sporttery_prob
        better = (
            odds is not None
            and row.polymarket_odds is not None
            and odds > row.polymarket_odds
        )
    else:
        odds = row.polymarket_odds
        prob = row.polymarket_prob
        better = (
            odds is not None
            and row.sporttery_odds is not None
            and odds > row.sporttery_odds
        )

    odds_text = f"{odds:.2f}" if odds is not None else "—"
    prob_text = f"{prob * 100:.1f}%" if prob is not None else ""
    better_class = " better" if better else ""
    sub = f'<span class="odds-sub">{prob_text}</span>' if prob_text else ""
    return (
        f'<div class="odds-cell {side}{better_class}">'
        f'<span class="odds-value">{odds_text}</span>{sub}</div>'
    )


def render_match_details(match: MatchView, index: int) -> str:
    blocks: list[str] = []
    primary = _primary_comparison(match)

    for comparison in match.comparisons:
        if primary and comparison.title == primary.title:
            continue
        blocks.append(render_detail_comparison(comparison))

    detail_markets = [market for market in match.markets if market.name != "胜平负"]
    detail_markets.sort(
        key=lambda market: (
            0 if market.name == "精确比分" else 1 if market.name == "半场结果" else 2,
            market.name,
        )
    )
    for market in detail_markets:
        blocks.append(render_detail_market(market))

    if not blocks:
        return ""

    body = "\n".join(blocks)
    return f"""
<details class="details-toggle">
  <summary>比分详情</summary>
  <div class="details-body">{body}</div>
</details>"""


def _get_comparison_by_title(match: MatchView, title: str) -> OddsComparison | None:
    for comparison in match.comparisons:
        if comparison.title == title:
            return comparison
    return None


def render_detail_comparison(comparison: OddsComparison) -> str:
    rows = "\n".join(render_detail_comparison_row(row) for row in comparison.rows)
    return f"""
<div class="detail-block">
  <h3>{html.escape(comparison.title)}</h3>
  <p class="detail-note">{html.escape(comparison.note)}</p>
  <table class="data-table">
    <thead>
      <tr>
        <th>结果</th>
        <th>体育彩票</th>
        <th>Polymarket</th>
        <th>Polymarket 概率</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def render_detail_comparison_row(row: ComparisonRow) -> str:
    lottery = f"{row.sporttery_odds:.2f}" if row.sporttery_odds is not None else "—"
    poly_odds = f"{row.polymarket_odds:.2f}" if row.polymarket_odds is not None else "—"
    poly_prob = f"{row.polymarket_prob * 100:.1f}%" if row.polymarket_prob is not None else "—"
    lottery_class = ""
    poly_class = ""
    if row.sporttery_odds and row.polymarket_odds:
        if row.sporttery_odds > row.polymarket_odds:
            lottery_class = ' style="color:var(--lottery);font-weight:700"'
        elif row.polymarket_odds > row.sporttery_odds:
            poly_class = ' style="color:var(--poly);font-weight:700"'
    return f"""
<tr>
  <td>{html.escape(row.outcome)}</td>
  <td class="num"{lottery_class}>{lottery}</td>
  <td class="num"{poly_class}>{poly_odds}</td>
  <td class="num">{poly_prob}</td>
</tr>"""


def render_detail_market(market: MarketGroup) -> str:
    rows = "\n".join(render_detail_option(option) for option in market.options[:12])
    more = ""
    if len(market.options) > 12:
        more = f'<p class="detail-note">另有 {len(market.options) - 12} 个选项未展示</p>'
    return f"""
<div class="detail-block">
  <h3>{html.escape(market.name)}</h3>
  <table class="data-table">
    <thead><tr><th>选项</th><th>概率</th><th>参考欧赔</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  {more}
</div>"""


def render_detail_option(option: MarketOption) -> str:
    return f"""
<tr>
  <td>{html.escape(option.label)}</td>
  <td class="num">{option.probability * 100:.1f}%</td>
  <td class="num">{option.odds:.2f}</td>
</tr>"""


def team_name_zh(name: str) -> str:
    return TEAM_PROFILES.get(name, (name, "", ""))[0]


def team_flag(name: str) -> str:
    return TEAM_PROFILES.get(name, ("", "🏳️", ""))[1]


def team_flag_code(name: str) -> str:
    return TEAM_PROFILES.get(name, ("", "", ""))[2]


def team_flag_url(name: str) -> str | None:
    code = team_flag_code(name)
    if not code:
        return None
    return f"{FLAG_CDN}/{code}.png"


def render_team_flag(name: str) -> str:
    url = team_flag_url(name)
    if url:
        return (
            f'<img class="team-flag" src="{html.escape(url)}" '
            f'alt="{html.escape(team_name_zh(name))} 国旗" loading="lazy" width="44" height="32">'
        )
    return f'<span class="team-flag-fallback">{html.escape(team_flag(name))}</span>'

