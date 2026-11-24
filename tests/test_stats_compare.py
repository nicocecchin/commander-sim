import pytest

from commander_sim.stats.compare import compare_decks
from tests.game_factory import FIELD, games_against_field, make_game


def test_difference_interval_and_no_warning_for_a_big_matched_sample():
    games = games_against_field("a", 300, 1200) + games_against_field("b", 360, 1200)
    result = compare_decks(games, "a", "b")
    assert result.difference == pytest.approx(0.05)
    assert result.interval[0] < 0.05 < result.interval[1]
    assert result.head_to_head_games == 0
    assert result.warnings == ()


def test_small_sample_warns_how_little_it_can_resolve():
    games = games_against_field("a", 10, 40) + games_against_field("b", 12, 40)
    result = compare_decks(games, "a", "b")
    assert any("Too few games" in w for w in result.warnings)
    assert result.min_detectable > 0.05


def test_different_opponent_fields_are_flagged():
    games = games_against_field("a", 25, 100) + [
        make_game(("b", "p", "q", "r"), 1) for _ in range(100)
    ]
    result = compare_decks(games, "a", "b")
    assert any("same mix of opponents" in w for w in result.warnings)


def test_different_seat_distributions_are_flagged():
    games = games_against_field("a", 25, 100) + [make_game(("b", *FIELD), 1) for _ in range(100)]
    result = compare_decks(games, "a", "b")
    assert any("same seats" in w for w in result.warnings)


def test_head_to_head_games_are_flagged():
    games = (
        games_against_field("a", 25, 100)
        + games_against_field("b", 25, 100)
        + [make_game(("a", "b", "x", "y"), 1)]
    )
    assert compare_decks(games, "a", "b").head_to_head_games == 1


def test_unknown_deck_cannot_be_compared():
    with pytest.raises(ValueError):
        compare_decks(games_against_field("a", 5, 20), "a", "nope")
