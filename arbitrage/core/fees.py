from __future__ import annotations


def odds_from_probability(probability: float) -> float:
    if probability <= 0 or probability >= 1:
        raise ValueError("probability must be between 0 and 1")
    return 1 / probability


def polymarket_effective_odds(probability: float, fee_rate: float = 0.03) -> float:
    effective_probability = probability - fee_rate * probability * (1 - probability)
    return odds_from_probability(effective_probability)


def kalshi_effective_odds(probability: float, fee_multiplier: float = 0.07) -> float:
    effective_probability = probability - fee_multiplier * probability * (1 - probability)
    return odds_from_probability(effective_probability)


def smarkets_effective_odds(raw_odds: float, commission_rate: float = 0.02) -> float:
    if raw_odds <= 1:
        raise ValueError("raw_odds must be greater than 1")
    return 1 + (raw_odds - 1) * (1 - commission_rate)


def probability_percent_to_odds(probability_percent: float) -> float:
    if probability_percent <= 0 or probability_percent >= 100:
        raise ValueError("probability_percent must be between 0 and 100")
    return 100 / probability_percent

