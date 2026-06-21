from arbitrage.core.normalizer import normalize_team_name


def test_unlisted_team_is_not_fuzzy_matched_to_wrong_alias() -> None:
    aliases = {"germany": ["Germany", "GER", "德国"]}

    assert normalize_team_name("Algeria", aliases) == "algeria"


def test_exact_alias_still_normalizes() -> None:
    aliases = {"saudi_arabia": ["Saudi Arabia", "Saudi", "KSA", "沙特"]}

    assert normalize_team_name("Saudi", aliases) == "saudi_arabia"

