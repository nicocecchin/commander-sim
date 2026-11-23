import pytest

from commander_sim.stats.compare import compare_decks
from tests.game_factory import make_game

FIELD = ("x", "y", "z")


def pods_for(variant: str, wins: int, games: int):
    """`games` games of `variant` against the field, rotated through the seats."""
    out = []
    for i in range(games):
        shift = i % 4
        seating = (*FIELD[:shift], variant, *FIELD[shift:])
        out.append(make_game(seating, shift + 1 if i < wins else (shift + 1) % 4 + 1))
    return out


def test_difference_interval_and_no_warning_for_a_big_matched_sample():
    games = pods_for("a", 300, 1200) + pods_for("b", 360, 1200)
    result = compare_decks(games, "a", "b")
    assert result.difference == pytest.approx(0.05)
    assert result.interval[0] < 0.05 < result.interval[1]
    assert result.head_to_head_games == 0
    assert result.warnings == ()


def test_small_sample_warns_how_little_it_can_resolve():
    games = pods_for("a", 10, 40) + pods_for("b", 12, 40)
    result = compare_decks(games, "a", "b")
    assert any("Too few games" in w for w in result.warnings)
    assert result.min_detectable > 0.05


def test_different_opponent_fields_are_flagged():
    games = pods_for("a", 25, 100) + [make_game(("b", "p", "q", "r"), 1) for _ in range(100)]
    result = compare_decks(games, "a", "b")
    assert any("same mix of opponents" in w for w in result.warnings)


def test_different_seat_distributions_are_flagged():
    games = pods_for("a", 25, 100) + [make_game(("b", *FIELD), 1) for _ in range(100)]
    result = compare_decks(games, "a", "b")
    assert any("same seats" in w for w in result.warnings)


def test_head_to_head_games_are_flagged():
    games = pods_for("a", 25, 100) + pods_for("b", 25, 100) + [make_game(("a", "b", "x", "y"), 1)]
    assert compare_decks(games, "a", "b").head_to_head_games == 1


def test_unknown_deck_cannot_be_compared():
    with pytest.raises(ValueError):
        compare_decks(pods_for("a", 5, 20), "a", "nope")
