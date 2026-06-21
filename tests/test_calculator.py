from __future__ import annotations

from datetime import datetime, timezone

from arbitrage.core.calculator import find_arbitrage_opportunities
from arbitrage.models import OddsEntry


def test_finds_three_way_arbitrage_with_effective_odds() -> None:
    kickoff = datetime(2026, 6, 22, tzinfo=timezone.utc)
    entries = [
        OddsEntry(
            platform="sporttery",
            match_id="match",
            home_team="spain",
            away_team="saudi_arabia",
            kickoff_time=kickoff,
            fetched_at=kickoff,
            odds_home=2.2,
            odds_draw=4.2,
            odds_away=3.0,
            raw_odds_home=2.25,
            raw_odds_draw=4.3,
            raw_odds_away=3.0,
        ),
        OddsEntry(
            platform="smarkets",
            match_id="match",
            home_team="spain",
            away_team="saudi_arabia",
            kickoff_time=kickoff,
            fetched_at=kickoff,
            odds_home=2.0,
            odds_draw=4.0,
            odds_away=4.0,
            raw_odds_home=2.0,
            raw_odds_draw=4.0,
            raw_odds_away=4.1,
        )
    ]

    opportunities = find_arbitrage_opportunities({"match": entries}, stake_amount=100)

    assert len(opportunities) == 1
    opportunity = opportunities[0]
    assert opportunity.market_type == "three_way"
    assert opportunity.profit_margin > 0
    assert round(opportunity.best_home.stake + opportunity.best_draw.stake + opportunity.best_away.stake, 2) == 100


def test_finds_two_way_arbitrage_without_treating_not_home_as_away() -> None:
    kickoff = datetime(2026, 6, 22, tzinfo=timezone.utc)
    entries = [
        OddsEntry(
            platform="polymarket",
            match_id="match",
            home_team="spain",
            away_team="saudi_arabia",
            kickoff_time=kickoff,
            fetched_at=kickoff,
            odds_home=2.1,
            odds_not_home=1.9,
            raw_odds_home=2.12,
            raw_odds_not_home=1.9,
        ),
        OddsEntry(
            platform="kalshi",
            match_id="match",
            home_team="spain",
            away_team="saudi_arabia",
            kickoff_time=kickoff,
            fetched_at=kickoff,
            odds_home=2.0,
            odds_not_home=2.05,
            raw_odds_home=2.0,
            raw_odds_not_home=2.08,
        )
    ]

    opportunities = find_arbitrage_opportunities({"match": entries}, stake_amount=100)

    assert len(opportunities) == 1
    assert opportunities[0].market_type == "two_way"
    assert opportunities[0].best_away is None
    assert opportunities[0].best_not_home is not None


def test_ignores_non_arbitrage() -> None:
    kickoff = datetime(2026, 6, 22, tzinfo=timezone.utc)
    entries = [
        OddsEntry(
            platform="sporttery",
            match_id="match",
            home_team="spain",
            away_team="saudi_arabia",
            kickoff_time=kickoff,
            fetched_at=kickoff,
            odds_home=1.5,
            odds_draw=3.0,
            odds_away=5.0,
            raw_odds_home=1.5,
            raw_odds_draw=3.0,
            raw_odds_away=5.0,
        )
    ]

    assert find_arbitrage_opportunities({"match": entries}, stake_amount=100) == []


def test_ignores_single_platform_three_way_even_if_index_is_profitable() -> None:
    kickoff = datetime(2026, 6, 22, tzinfo=timezone.utc)
    entries = [
        OddsEntry(
            platform="smarkets",
            match_id="match",
            home_team="spain",
            away_team="saudi_arabia",
            kickoff_time=kickoff,
            fetched_at=kickoff,
            odds_home=2.2,
            odds_draw=4.2,
            odds_away=4.0,
            raw_odds_home=2.25,
            raw_odds_draw=4.3,
            raw_odds_away=4.1,
        )
    ]

    assert find_arbitrage_opportunities({"match": entries}, stake_amount=100) == []


def test_ignores_single_platform_two_way_even_if_index_is_profitable() -> None:
    kickoff = datetime(2026, 6, 22, tzinfo=timezone.utc)
    entries = [
        OddsEntry(
            platform="polymarket",
            match_id="match",
            home_team="spain",
            away_team="saudi_arabia",
            kickoff_time=kickoff,
            fetched_at=kickoff,
            odds_home=2.1,
            odds_not_home=2.05,
            raw_odds_home=2.12,
            raw_odds_not_home=2.08,
        )
    ]

    assert find_arbitrage_opportunities({"match": entries}, stake_amount=100) == []

