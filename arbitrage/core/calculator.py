from __future__ import annotations

from arbitrage.config import settings
from arbitrage.models import (
    ArbitrageOpportunity,
    BestOutcome,
    OddsEntry,
    OddsQuote,
    Outcome,
)


def find_arbitrage_opportunities(
    groups: dict[str, list[OddsEntry]],
    stake_amount: float = settings.stake_amount,
) -> list[ArbitrageOpportunity]:
    opportunities: list[ArbitrageOpportunity] = []
    for match_id, entries in groups.items():
        if not entries:
            continue
        three_way = _compute_three_way(match_id, entries, stake_amount)
        if three_way:
            opportunities.append(three_way)
        two_way = _compute_two_way(match_id, entries, stake_amount)
        if two_way:
            opportunities.append(two_way)
    return sorted(opportunities, key=lambda item: item.profit_margin, reverse=True)


def _compute_three_way(
    match_id: str, entries: list[OddsEntry], stake_amount: float
) -> ArbitrageOpportunity | None:
    best_home = _best_quote(entries, "home")
    best_draw = _best_quote(entries, "draw")
    best_away = _best_quote(entries, "away")
    if not best_home or not best_draw or not best_away:
        return None

    best_quotes = [best_home, best_draw, best_away]
    if not _uses_multiple_platforms(best_quotes):
        return None

    arbitrage_index = sum(1 / quote.effective_odds for quote in best_quotes)
    if arbitrage_index >= settings.arbitrage_threshold:
        return None

    best_outcomes = [
        _to_best_outcome(quote, arbitrage_index, stake_amount) for quote in best_quotes
    ]
    first = entries[0]
    return ArbitrageOpportunity(
        match_id=match_id,
        home_team=first.home_team,
        away_team=first.away_team,
        kickoff_time=first.kickoff_time,
        market_type="three_way",
        best_home=best_outcomes[0],
        best_draw=best_outcomes[1],
        best_away=best_outcomes[2],
        best_not_home=None,
        arbitrage_index=arbitrage_index,
        profit_margin=(1 - arbitrage_index) * 100,
        guaranteed_return=stake_amount / arbitrage_index,
    )


def _compute_two_way(
    match_id: str, entries: list[OddsEntry], stake_amount: float
) -> ArbitrageOpportunity | None:
    best_home = _best_quote(entries, "home")
    best_not_home = _best_quote(entries, "not_home")
    if not best_home or not best_not_home:
        return None

    best_quotes = [best_home, best_not_home]
    if not _uses_multiple_platforms(best_quotes):
        return None

    arbitrage_index = sum(1 / quote.effective_odds for quote in best_quotes)
    if arbitrage_index >= settings.arbitrage_threshold:
        return None

    best_home_outcome, best_not_home_outcome = [
        _to_best_outcome(quote, arbitrage_index, stake_amount) for quote in best_quotes
    ]
    first = entries[0]
    return ArbitrageOpportunity(
        match_id=match_id,
        home_team=first.home_team,
        away_team=first.away_team,
        kickoff_time=first.kickoff_time,
        market_type="two_way",
        best_home=best_home_outcome,
        best_draw=None,
        best_away=None,
        best_not_home=best_not_home_outcome,
        arbitrage_index=arbitrage_index,
        profit_margin=(1 - arbitrage_index) * 100,
        guaranteed_return=stake_amount / arbitrage_index,
    )


def _best_quote(entries: list[OddsEntry], outcome: Outcome) -> OddsQuote | None:
    quotes = [quote for entry in entries for quote in entry.quotes() if quote.outcome == outcome]
    if not quotes:
        return None
    return max(quotes, key=lambda quote: quote.effective_odds)


def _uses_multiple_platforms(quotes: list[OddsQuote]) -> bool:
    return len({quote.platform for quote in quotes}) >= 2


def _to_best_outcome(
    quote: OddsQuote, arbitrage_index: float, stake_amount: float
) -> BestOutcome:
    stake = (1 / quote.effective_odds) / arbitrage_index * stake_amount
    return BestOutcome(
        outcome=quote.outcome,
        raw_odds=quote.raw_odds,
        effective_odds=quote.effective_odds,
        platform=quote.platform,
        stake=stake,
        source_url=quote.source_url,
    )

