from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def parse_matchup(text: str) -> tuple[str, str] | None:
    patterns = [
        r"will\s+(.+?)\s+beat\s+(.+?)(?:\?|$)",
        r"(.+?)\s+to\s+win\s+(?:vs|against)\s+(.+?)(?:\?|$)",
        r"(.+?)\s+(?:vs\.?|v\.?|versus)\s+(.+?)(?:\?|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            home, away = match.group(1).strip(), match.group(2).strip()
            if home and away:
                return home, away
    return None

