from __future__ import annotations

import json
import re
from pathlib import Path

from rapidfuzz import fuzz, process

from arbitrage.config import settings


ALIASES_PATH = Path(__file__).resolve().parents[1] / "team_aliases.json"


def load_team_aliases(path: Path = ALIASES_PATH) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_team_name(team_name: str, aliases: dict[str, list[str]] | None = None) -> str:
    aliases = aliases if aliases is not None else load_team_aliases()
    cleaned = _clean_team_name(team_name)
    if not cleaned:
        return cleaned

    choices: dict[str, str] = {}
    for canonical, alias_list in aliases.items():
        choices[_clean_team_name(canonical)] = canonical
        for alias in alias_list:
            choices[_clean_team_name(alias)] = canonical

    if cleaned in choices:
        return choices[cleaned]

    match = process.extractOne(cleaned, choices.keys(), scorer=fuzz.WRatio)
    if (
        match
        and match[1] >= settings.fuzzy_match_threshold
        and _has_compatible_prefix(cleaned, match[0])
    ):
        return choices[match[0]]

    return cleaned.replace(" ", "_")


def _clean_team_name(team_name: str) -> str:
    text = team_name.casefold().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^[^\w\u4e00-\u9fff]+|[^\w\u4e00-\u9fff]+$", "", text)
    return text


def _has_compatible_prefix(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left[0].isalnum() and right[0].isalnum():
        return left[0] == right[0]
    return True

