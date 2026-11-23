"""A/B comparison of two decks that faced comparable fields. Pure functions."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from commander_sim.forge.output import Outcome
from commander_sim.stats.intervals import (
    difference_interval,
    min_detectable_difference,
    two_proportion_p_value,
)
from commander_sim.stats.winrates import DeckStats, deck_stats
from commander_sim.storage.results import GameRecord

RESOLVABLE_DIFFERENCE = 0.05
MAX_FIELD_DISTANCE = 0.05


@dataclass(frozen=True)
class Comparison:
    a: DeckStats
    b: DeckStats
    difference: float  # winrate of b minus winrate of a
    interval: tuple[float, float]
    p_value: float
    min_detectable: float
    head_to_head_games: int
    warnings: tuple[str, ...]


def _total_variation(first: Counter, second: Counter) -> float:
    total_first, total_second = sum(first.values()), sum(second.values())
    if not total_first or not total_second:
        return 1.0
    keys = first.keys() | second.keys()
    return sum(abs(first[k] / total_first - second[k] / total_second) for k in keys) / 2


def _opponents_and_seats(
    games: Iterable[GameRecord], deck: str, other: str
) -> tuple[Counter, Counter]:
    opponents: Counter = Counter()
    seats: Counter = Counter()
    for game in games:
        names = [seat.deck for seat in game.seats]
        seats[names.index(deck)] += 1
        opponents.update(name for name in names if name not in (deck, other))
    return opponents, seats


def compare_decks(games: list[GameRecord], deck_a: str, deck_b: str) -> Comparison:
    """Compare two decks' winrates. Raises ValueError if either has no decided games."""
    valid = [g for g in games if g.outcome is not Outcome.CRASH]
    games_a = [g for g in valid if any(s.deck == deck_a for s in g.seats)]
    games_b = [g for g in valid if any(s.deck == deck_b for s in g.seats)]
    stats = {s.deck: s for s in deck_stats(valid)}
    a, b = stats.get(deck_a), stats.get(deck_b)
    if not a or not b or not a.decided or not b.decided:
        raise ValueError("Both decks need at least one decided game to be compared")

    warnings = []
    head_to_head = sum(1 for g in games_a if any(s.deck == deck_b for s in g.seats))
    if head_to_head:
        warnings.append(
            f"{head_to_head} games had both decks at the table; their results are not "
            "independent, so the interval is optimistic."
        )
    opponents_a, seats_a = _opponents_and_seats(games_a, deck_a, deck_b)
    opponents_b, seats_b = _opponents_and_seats(games_b, deck_b, deck_a)
    if _total_variation(opponents_a, opponents_b) > MAX_FIELD_DISTANCE:
        warnings.append("The two decks did not face the same mix of opponents.")
    if _total_variation(seats_a, seats_b) > MAX_FIELD_DISTANCE:
        warnings.append("The two decks did not sit in the same seats equally often.")
    detectable = min_detectable_difference(a.decided, b.decided)
    if detectable > RESOLVABLE_DIFFERENCE:
        warnings.append(
            f"Too few games: differences smaller than {detectable * 100:.1f} points cannot be "
            f"told apart from noise (about 1000 decided games per deck are needed for "
            f"{RESOLVABLE_DIFFERENCE * 100:.0f} points)."
        )
    return Comparison(
        a=a,
        b=b,
        difference=b.winrate - a.winrate,
        interval=difference_interval(a.wins, a.decided, b.wins, b.decided),
        p_value=two_proportion_p_value(a.wins, a.decided, b.wins, b.decided),
        min_detectable=detectable,
        head_to_head_games=head_to_head,
        warnings=tuple(warnings),
    )
