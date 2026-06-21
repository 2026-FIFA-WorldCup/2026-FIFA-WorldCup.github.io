from arbitrage.fetchers.sporttery_web import format_handicap_label


def test_format_handicap_label_home_gives_two() -> None:
    assert format_handicap_label("-2") == "主让2球"


def test_format_handicap_label_away_gives_one() -> None:
    assert format_handicap_label("+1") == "客让1球"
