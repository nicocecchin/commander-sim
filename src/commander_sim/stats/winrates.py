"""Winrates per deck and per seat, from stored games. Pure functions."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from commander_sim.forge.output import Outcome
from commander_sim.stats.intervals import wilson_interval
from commander_sim.storage.results import GameRecord


@dataclass(frozen=True)
class DeckStats:
    """`winrate` is wins / decided games; timeouts are counted separately, crashes not at all."""

    deck: str
    appearances: int
    wins: int
    timeouts: int
    crashes: int

    @property
    def decided(self) -> int:
        return self.appearances - self.timeouts

    @property
    def winrate(self) -> float:
        return self.wins / self.decided if self.decided else 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return wilson_interval(self.wins, self.decided)

    @property
    def timeout_rate(self) -> float:
        return self.timeouts / self.appearances if self.appearances else 0.0


@dataclass(frozen=True)
class SeatStats:
    seat: int
    decided: int
    wins: int

    @property
    def winrate(self) -> float:
        return self.wins / self.decided if self.decided else 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return wilson_interval(self.wins, self.decided)


def deck_stats(games: Iterable[GameRecord]) -> list[DeckStats]:
    """Per-deck results, best winrate first. Crashed games are infrastructure failures: they
    count toward `crashes` only, never as a loss."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for game in games:
        for seat_number, seat in enumerate(game.seats, start=1):
            entry = counts[seat.deck]
            if game.outcome is Outcome.CRASH:
                entry["crashes"] += 1
                continue
            entry["appearances"] += 1
            entry["timeouts"] += game.outcome is Outcome.TIMEOUT
            entry["wins"] += game.winner_seat == seat_number
    stats = [
        DeckStats(deck, c["appearances"], c["wins"], c["timeouts"], c["crashes"])
        for deck, c in counts.items()
    ]
    return sorted(stats, key=lambda s: (-s.winrate, s.deck))


def seat_stats(games: Iterable[GameRecord]) -> list[SeatStats]:
    decided: dict[int, int] = defaultdict(int)
    wins: dict[int, int] = defaultdict(int)
    for game in games:
        if game.outcome is not Outcome.WIN:
            continue
        for seat_number in range(1, len(game.seats) + 1):
            decided[seat_number] += 1
        wins[game.winner_seat] += 1
    return [SeatStats(seat, decided[seat], wins[seat]) for seat in sorted(decided)]


def deck_versions(games: Iterable[GameRecord]) -> dict[str, set[str]]:
    """Decks that appear with more than one card list (same file name, different contents)."""
    hashes: dict[str, set[str]] = defaultdict(set)
    for game in games:
        for seat in game.seats:
            hashes[seat.deck].add(seat.deck_hash)
    return {deck: found for deck, found in hashes.items() if len(found) > 1}
