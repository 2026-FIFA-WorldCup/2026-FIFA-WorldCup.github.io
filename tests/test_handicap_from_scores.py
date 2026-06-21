from arbitrage.core.handicap_from_scores import (
    aggregate_outcome_probs,
    handicap_outcome,
    parse_score_from_label,
    probs_to_odds,
)


def test_parse_score_from_label() -> None:
    line = parse_score_from_label("西班牙 3 - 0 沙特阿拉伯")
    assert line is not None
    assert line.home_goals == 3
    assert line.away_goals == 0


def test_handicap_home_gives_two() -> None:
    assert handicap_outcome(3, 0, -2) == "home"
    assert handicap_outcome(2, 0, -2) == "draw"
    assert handicap_outcome(1, 0, -2) == "away"


def test_aggregate_handicap_from_scores() -> None:
    scores = [
        (3, 0, 0.165),
        (2, 0, 0.145),
        (1, 0, 0.075),
        (0, 0, 0.0265),
    ]
    probs = aggregate_outcome_probs(scores, goal_line=-2)
    assert probs["home"] > probs["draw"] > 0
    odds = probs_to_odds(probs)
    assert odds["home"] < odds["draw"]
