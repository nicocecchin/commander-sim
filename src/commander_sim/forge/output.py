"""Parse the stdout of ``forge sim`` (full game log, not ``-q``) into structured game results.

The full log is needed for the turn count: quiet mode only prints Forge's `Game Outcome: Turn N`,
which is about half the real turn counter in games with more than two players.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

_HEADER = re.compile(r"^(?P<players>Ai\(1\)-.+?) - \w+ games? of\b.*?(?: seed (?P<seed>-?\d+))?$")
_PLAYER = re.compile(r"Ai\((?P<seat>\d+)\)-(?P<deck>.+?)(?= vs Ai\(\d+\)-| - \w+ games? of|$)")
_TURN = re.compile(r"^Turn: Turn (?P<turn>\d+) \(Ai\((?P<seat>\d+)\)-")
_GAME_RESULT = re.compile(
    r"^Game Result: Game (?P<number>\d+) ended in (?P<ms>\d+) ms\. "
    r"Ai\((?P<seat>\d+)\)-.+ has won!$"
)
_TIMEOUT_MARKER = "Stopping slow match as draw"


class Outcome(StrEnum):
    WIN = "win"
    TIMEOUT = "timeout"
    CRASH = "crash"  # Forge never reports this; the runner records it when a launch fails


@dataclass(frozen=True)
class GameResult:
    """`turns` counts every player's turn; a round is one pass around the table."""

    number: int
    outcome: Outcome
    winner_seat: int | None
    turns: int | None
    rounds: int | None
    duration_ms: int | None


def count_rounds(turn_seats: list[int], seat_count: int) -> int:
    """Rounds played, from the seat of each turn in order.

    A new round starts whenever the turn order wraps past the starting player's position, so
    players eliminated mid-game do not inflate the count. An extra turn (the same player twice
    in a row) is counted as a new round.
    """
    if not turn_seats:
        return 0
    starter = turn_seats[0]
    positions = [(seat - starter) % seat_count for seat in turn_seats]
    pairs = zip(positions, positions[1:], strict=False)
    return 1 + sum(1 for before, after in pairs if after <= before)


@dataclass(frozen=True)
class SimOutput:
    seed: int | None
    deck_names: tuple[str, ...]
    games: tuple[GameResult, ...]


def parse_sim_output(text: str) -> SimOutput:
    """Parse the output of a sim run.

    On a timeout Forge still prints a "has won" line for every seat, so the timeout marker
    takes precedence over the winner lines.
    """
    seed: int | None = None
    deck_names: tuple[str, ...] = ()
    games: list[GameResult] = []
    timed_out = False
    turn_seats: list[int] = []
    last_turn = 0

    for line in text.splitlines():
        if _TIMEOUT_MARKER in line:
            timed_out = True
        elif match := _TURN.match(line):
            last_turn = int(match["turn"])
            turn_seats.append(int(match["seat"]))
        elif match := _GAME_RESULT.match(line):
            seat_count = len(deck_names) or max(turn_seats, default=1)
            games.append(
                GameResult(
                    number=int(match["number"]),
                    outcome=Outcome.TIMEOUT if timed_out else Outcome.WIN,
                    winner_seat=None if timed_out else int(match["seat"]),
                    turns=last_turn or None,
                    rounds=count_rounds(turn_seats, seat_count) or None,
                    duration_ms=int(match["ms"]),
                )
            )
            timed_out, turn_seats, last_turn = False, [], 0
        elif not deck_names and (match := _HEADER.match(line)):
            seed = int(match["seed"]) if match["seed"] else None
            deck_names = tuple(m["deck"] for m in _PLAYER.finditer(match["players"]))

    return SimOutput(seed=seed, deck_names=deck_names, games=tuple(games))
