"""Build stored-game records for statistics tests."""

from commander_sim.forge.output import Outcome
from commander_sim.pilots import Pilot
from commander_sim.storage.results import GameRecord, Seat


def make_game(
    decks: tuple[str, ...],
    winner_seat: int | None,
    outcome: Outcome | None = None,
    hashes: dict[str, str] | None = None,
) -> GameRecord:
    """A game with `decks` in seat order. Outcome defaults to WIN, or TIMEOUT without a winner."""
    outcome = outcome or (Outcome.WIN if winner_seat else Outcome.TIMEOUT)
    seats = tuple(Seat(d, (hashes or {}).get(d, f"h-{d}"), Pilot.FORGE_AI) for d in decks)
    return GameRecord("run", 0, 1, outcome, winner_seat, 20, 1000, seats)
