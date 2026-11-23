"""Parse the stdout of ``forge sim ... -q`` into structured game results."""

import re
from dataclasses import dataclass
from enum import StrEnum

_HEADER = re.compile(r"^(?P<players>Ai\(1\)-.+?) - \w+ games? of\b.*?(?: seed (?P<seed>-?\d+))?$")
_PLAYER = re.compile(r"Ai\((?P<seat>\d+)\)-(?P<deck>.+?)(?= vs Ai\(\d+\)-| - \w+ games? of|$)")
_TURNS = re.compile(r"^Game Outcome: Turn (?P<turns>\d+)$")
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
    number: int
    outcome: Outcome
    winner_seat: int | None
    turns: int | None
    duration_ms: int | None


@dataclass(frozen=True)
class SimOutput:
    seed: int | None
    deck_names: tuple[str, ...]
    games: tuple[GameResult, ...]


def parse_sim_output(text: str) -> SimOutput:
    """Parse quiet-mode sim output.

    On a timeout Forge still prints a "has won" line for every seat, so the timeout marker
    takes precedence over the winner lines.
    """
    seed: int | None = None
    deck_names: tuple[str, ...] = ()
    games: list[GameResult] = []
    timed_out = False
    turns = 0

    for line in text.splitlines():
        if _TIMEOUT_MARKER in line:
            timed_out = True
        elif match := _TURNS.match(line):
            turns = int(match["turns"])
        elif match := _GAME_RESULT.match(line):
            games.append(
                GameResult(
                    number=int(match["number"]),
                    outcome=Outcome.TIMEOUT if timed_out else Outcome.WIN,
                    winner_seat=None if timed_out else int(match["seat"]),
                    turns=turns,
                    duration_ms=int(match["ms"]),
                )
            )
            timed_out = False
        elif not deck_names and (match := _HEADER.match(line)):
            seed = int(match["seed"]) if match["seed"] else None
            deck_names = tuple(m["deck"] for m in _PLAYER.finditer(match["players"]))

    return SimOutput(seed=seed, deck_names=deck_names, games=tuple(games))
