from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal


Outcome = Literal["home", "draw", "away", "not_home"]
Platform = Literal["polymarket", "kalshi", "smarkets", "sporttery"]


@dataclass(frozen=True)
class OddsQuote:
    outcome: Outcome
    raw_odds: float
    effective_odds: float
    platform: Platform
    source_url: str | None


@dataclass
class OddsEntry:
    platform: Platform
    match_id: str
    home_team: str
    away_team: str
    kickoff_time: datetime
    fetched_at: datetime
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None
    odds_not_home: float | None = None
    raw_odds_home: float | None = None
    raw_odds_draw: float | None = None
    raw_odds_away: float | None = None
    raw_odds_not_home: float | None = None
    source_id: str | None = None
    source_url: str | None = None
    metadata: dict[str, Any] | None = None

    def quotes(self) -> list[OddsQuote]:
        quotes: list[OddsQuote] = []
        mapping: list[tuple[Outcome, float | None, float | None]] = [
            ("home", self.raw_odds_home, self.odds_home),
            ("draw", self.raw_odds_draw, self.odds_draw),
            ("away", self.raw_odds_away, self.odds_away),
            ("not_home", self.raw_odds_not_home, self.odds_not_home),
        ]
        for outcome, raw_odds, effective_odds in mapping:
            if raw_odds is not None and effective_odds is not None:
                quotes.append(
                    OddsQuote(
                        outcome=outcome,
                        raw_odds=raw_odds,
                        effective_odds=effective_odds,
                        platform=self.platform,
                        source_url=self.source_url,
                    )
                )
        return quotes

    def to_json_dict(self) -> dict[str, Any]:
        return _serialize_dataclass(self)


@dataclass(frozen=True)
class BestOutcome:
    outcome: Outcome
    raw_odds: float
    effective_odds: float
    platform: Platform
    stake: float
    source_url: str | None


@dataclass
class ArbitrageOpportunity:
    match_id: str
    home_team: str
    away_team: str
    kickoff_time: datetime
    market_type: Literal["two_way", "three_way"]
    best_home: BestOutcome
    best_draw: BestOutcome | None
    best_away: BestOutcome | None
    best_not_home: BestOutcome | None
    arbitrage_index: float
    profit_margin: float
    guaranteed_return: float

    def to_json_dict(self) -> dict[str, Any]:
        return _serialize_dataclass(self)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_dataclass(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: _serialize_dataclass(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _serialize_dataclass(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_dataclass(item) for item in value]
    return value

