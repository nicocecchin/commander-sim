import numpy as np
import pytest

from commander_sim.stats.ratings import fit_ratings
from tests.game_factory import make_game

DECKS = ["a", "b", "c", "d", "e"]


def simulate_league(strengths: dict[str, float], games: int, seed: int):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(games):
        pod = tuple(rng.choice(DECKS, 4, replace=False))
        weights = np.array([strengths[d] for d in pod])
        winner = rng.choice(4, p=weights / weights.sum())
        out.append(make_game(pod, int(winner) + 1))
    return out


def test_recovers_known_strengths():
    truth = {"a": 3.0, "b": 1.5, "c": 1.0, "d": 1.0, "e": 0.5}
    ratings = fit_ratings(simulate_league(truth, 3000, seed=1), bootstrap=50)
    assert [r.deck for r in ratings][0] == "a"
    assert [r.deck for r in ratings][-1] == "e"
    top = ratings[0].strength
    for r in ratings:
        assert r.strength / top == pytest.approx(truth[r.deck] / truth["a"], rel=0.25)
        assert r.interval[0] - 0.02 < r.expected_winrate < r.interval[1] + 0.02
        assert r.interval[1] - r.interval[0] < 0.15


def test_equal_decks_get_equal_ratings():
    ratings = fit_ratings(simulate_league(dict.fromkeys(DECKS, 1.0), 4000, seed=2), bootstrap=20)
    assert (
        max(r.expected_winrate for r in ratings) - min(r.expected_winrate for r in ratings) < 0.04
    )


def test_deck_without_wins_stays_finite():
    games = [make_game(("a", "b", "c", "d"), 1) for _ in range(20)]
    ratings = {r.deck: r for r in fit_ratings(games, bootstrap=10)}
    assert 0 < ratings["b"].strength < ratings["a"].strength
    assert np.isfinite(ratings["b"].strength)


def test_no_decided_games_gives_no_ratings():
    assert fit_ratings([make_game(("a", "b", "c", "d"), None)]) == []
