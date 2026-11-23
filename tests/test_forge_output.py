from pathlib import Path

from commander_sim.forge.output import GameResult, Outcome, parse_sim_output

FIXTURES = Path(__file__).parent / "fixtures"
DECKS = (
    "Starter Commander - Black",
    "Starter Commander - Blue",
    "Starter Commander - Green",
    "Starter Commander - Red",
)


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_win_with_seed():
    parsed = parse_sim_output(read("win_seeded.txt"))
    assert parsed.seed == 42
    assert parsed.deck_names == DECKS
    assert parsed.games == (
        GameResult(number=1, outcome=Outcome.WIN, winner_seat=4, turns=34, duration_ms=87011),
    )


def test_timeout_is_not_a_win_despite_win_lines():
    parsed = parse_sim_output(read("timeout_all_win_lines.txt"))
    assert parsed.seed is None
    assert parsed.games == (
        GameResult(number=1, outcome=Outcome.TIMEOUT, winner_seat=None, turns=6, duration_ms=10104),
    )


def test_output_without_results_yields_no_games():
    assert parse_sim_output("Simulation mode\n").games == ()


def test_multiple_games():
    parsed = parse_sim_output(read("two_games_seeded.txt"))
    assert parsed.seed == 5
    assert parsed.deck_names == DECKS
    assert [(g.number, g.winner_seat, g.turns, g.duration_ms) for g in parsed.games] == [
        (1, 1, 35, 78753),
        (2, 1, 31, 34827),
    ]
