"""Deck strengths from who won each pod (Plackett-Luce, winner only), with bootstrap intervals.

Model: deck i wins a pod S with probability s_i / sum(s_j for j in S). Forge reports only the
winner, which is exactly the data this model needs, and the fit does not depend on game order.
A weak prior (half a win and half a loss against a reference deck of strength 1) keeps decks
with no wins finite and fixes the scale.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from commander_sim.forge.output import Outcome
from commander_sim.storage.results import GameRecord

_TOLERANCE = 1e-6
_MAX_ITERATIONS = 2000
_PRIOR_WIN = 0.5


@dataclass(frozen=True)
class Rating:
    deck: str
    strength: float
    expected_winrate: float  # winrate against pods of reference-strength decks
    interval: tuple[float, float]


def _fit(
    pods: np.ndarray,
    winners: np.ndarray,
    counts: np.ndarray,
    deck_count: int,
    start: np.ndarray | None = None,
) -> np.ndarray:
    """MM algorithm (Hunter 2004) on distinct (pod, winner) rows seen `counts` times each.

    `pods` is rows x seats of deck indices (-1 pads short pods). `start` is an optional initial
    guess for the strengths; a previous fit makes bootstrap refits converge quickly.
    """
    padded = np.where(pods < 0, deck_count, pods)
    wins = np.bincount(winners, weights=counts, minlength=deck_count + 1)[:deck_count] + _PRIOR_WIN
    strength = np.append(np.ones(deck_count) if start is None else start, 0.0)
    for _ in range(_MAX_ITERATIONS):
        totals = strength[padded].sum(axis=1)
        weights = np.repeat(counts / totals, padded.shape[1])
        exposure = np.bincount(padded.ravel(), weights=weights, minlength=deck_count + 1)
        updated = strength.copy()
        updated[:deck_count] = wins / (exposure[:deck_count] + 1.0 / (strength[:deck_count] + 1.0))
        converged = np.max(np.abs(updated - strength)) < _TOLERANCE * np.max(updated)
        strength = updated
        if converged:
            break
    return strength[:deck_count]


def _expected_winrate(strength: np.ndarray, pod_size: int) -> np.ndarray:
    return strength / (strength + pod_size - 1)


def fit_ratings(games: Sequence[GameRecord], bootstrap: int = 200, seed: int = 0) -> list[Rating]:
    """Rate every deck that appears in a game with a winner, best first."""
    decided = [g for g in games if g.outcome is Outcome.WIN]
    decks = sorted({seat.deck for g in decided for seat in g.seats})
    if not decided:
        return []
    index = {deck: i for i, deck in enumerate(decks)}
    width = max(len(g.seats) for g in decided)
    rows = np.full((len(decided), width + 1), -1, dtype=int)
    for row, game in enumerate(decided):
        rows[row, : len(game.seats)] = sorted(index[s.deck] for s in game.seats)
        rows[row, width] = index[game.winner.deck]
    unique, counts = np.unique(rows, axis=0, return_counts=True)
    pods, winners = unique[:, :width], unique[:, width]
    pod_size = int(np.median([len(g.seats) for g in decided]))

    strengths = _fit(pods, winners, counts, len(decks))
    point = _expected_winrate(strengths, pod_size)
    rng = np.random.default_rng(seed)
    samples = np.empty((bootstrap, len(decks)))
    for i in range(bootstrap):
        resampled = rng.multinomial(len(decided), counts / counts.sum())
        refit = _fit(pods, winners, resampled, len(decks), start=strengths)
        samples[i] = _expected_winrate(refit, pod_size)
    low, high = np.percentile(samples, [2.5, 97.5], axis=0)
    ratings = [
        Rating(deck, float(strengths[i]), float(point[i]), (float(low[i]), float(high[i])))
        for deck, i in index.items()
    ]
    return sorted(ratings, key=lambda r: -r.expected_winrate)
