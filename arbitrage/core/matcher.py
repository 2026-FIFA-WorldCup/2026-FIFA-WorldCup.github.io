from __future__ import annotations

import re
from dataclasses import replace
from datetime import timedelta

from arbitrage.config import settings
from arbitrage.core.normalizer import load_team_aliases, normalize_team_name
from arbitrage.models import OddsEntry


def match_entries(entries: list[OddsEntry]) -> dict[str, list[OddsEntry]]:
    aliases = load_team_aliases()
    groups: dict[str, list[OddsEntry]] = {}
    group_heads: dict[str, OddsEntry] = {}

    for entry in entries:
        normalized = _normalize_entry(entry, aliases)
        matched_id = _find_matching_group(normalized, group_heads)
        if matched_id is None:
            matched_id = make_match_id(
                normalized.home_team, normalized.away_team, normalized.kickoff_time
            )
            group_heads[matched_id] = replace(normalized, match_id=matched_id)
            groups[matched_id] = []

        normalized.match_id = matched_id
        groups[matched_id].append(normalized)

    return groups


def make_match_id(home_team: str, away_team: str, kickoff_time) -> str:
    kickoff_part = kickoff_time.strftime("%Y%m%d%H%M")
    home = _slug(home_team)
    away = _slug(away_team)
    return f"{home}_vs_{away}_{kickoff_part}"


def _normalize_entry(entry: OddsEntry, aliases: dict[str, list[str]]) -> OddsEntry:
    entry.home_team = normalize_team_name(entry.home_team, aliases)
    entry.away_team = normalize_team_name(entry.away_team, aliases)
    return entry


def _find_matching_group(entry: OddsEntry, group_heads: dict[str, OddsEntry]) -> str | None:
    window = timedelta(minutes=settings.team_match_time_window_minutes)
    for match_id, head in group_heads.items():
        if abs(entry.kickoff_time - head.kickoff_time) > window:
            continue
        if entry.home_team == head.home_team and entry.away_team == head.away_team:
            return match_id
    return None


def _slug(value: str) -> str:
    value = value.casefold().strip().replace(" ", "_")
    value = re.sub(r"[^a-z0-9_\u4e00-\u9fff]+", "", value)
    return value or "unknown"

