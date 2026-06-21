from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreLine:
    home_goals: int
    away_goals: int
    probability: float


def parse_score_from_label(label: str) -> ScoreLine | None:
    if not label or "other score" in label.casefold():
        return None
    match = re.search(r"(\d+)\s*-\s*(\d+)", label)
    if not match:
        return None
    home = int(match.group(1))
    away = int(match.group(2))
    return ScoreLine(home_goals=home, away_goals=away, probability=0.0)


def handicap_outcome(home_goals: int, away_goals: int, goal_line: float) -> str:
    adjusted_home = home_goals + goal_line
    if adjusted_home > away_goals:
        return "home"
    if adjusted_home == away_goals:
        return "draw"
    return "away"


def match_outcome(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    if home_goals == away_goals:
        return "draw"
    return "away"


def aggregate_outcome_probs(
    scores: list[tuple[int, int, float]],
    goal_line: float | None = None,
) -> dict[str, float]:
    totals = {"home": 0.0, "draw": 0.0, "away": 0.0}
    for home, away, probability in scores:
        if probability <= 0:
            continue
        if goal_line is None:
            outcome = match_outcome(home, away)
        else:
            outcome = handicap_outcome(home, away, goal_line)
        totals[outcome] += probability

    total = sum(totals.values())
    if total <= 0:
        return {}
    return {key: value / total for key, value in totals.items()}


def probs_to_odds(probs: dict[str, float]) -> dict[str, float]:
    odds: dict[str, float] = {}
    for key, prob in probs.items():
        if prob > 0:
            odds[key] = 1.0 / prob
    return odds
