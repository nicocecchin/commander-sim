from pathlib import Path

from commander_sim.forge.output import GameResult, Outcome, count_rounds, parse_sim_output

FIXTURES = Path(__file__).parent / "fixtures"
DECKS = (
    "Starter Commander - Black",
    "Starter Commander - Blue",
    "Starter Commander - Green",
    "Starter Commander - Red",
)


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_win_with_seed_counts_real_turns_and_rounds():
    parsed = parse_sim_output(read("win_seeded.txt"))
    assert parsed.seed == 42
    assert parsed.deck_names == DECKS
    assert parsed.games == (
        GameResult(1, Outcome.WIN, winner_seat=4, turns=68, rounds=18, duration_ms=81259),
    )


def test_timeout_is_not_a_win_despite_win_lines():
    parsed = parse_sim_output(read("timeout_all_win_lines.txt"))
    assert parsed.seed is None
    assert parsed.games == (
        GameResult(1, Outcome.TIMEOUT, winner_seat=None, turns=18, rounds=5, duration_ms=10106),
    )


def test_multiple_games_restart_the_turn_count():
    parsed = parse_sim_output(read("two_games_seeded.txt"))
    assert parsed.seed == 5
    assert parsed.deck_names == DECKS
    assert [(g.number, g.winner_seat, g.turns, g.rounds) for g in parsed.games] == [
        (1, 1, 70, 19),
        (2, 1, 62, 19),
    ]


def test_output_without_results_yields_no_games():
    assert parse_sim_output("Simulation mode\n").games == ()


def test_rounds_follow_the_table_order_from_the_starting_player():
    assert count_rounds([3, 4, 1, 2, 3, 4, 1, 2], 4) == 2
    assert count_rounds([3, 4, 1, 2, 3], 4) == 2


def test_rounds_are_not_inflated_by_eliminated_players():
    # Seats 1 and 2 are out after the first round; seats 3 and 4 keep alternating.
    assert count_rounds([3, 4, 1, 2, 3, 4, 3, 4], 4) == 3


def test_an_extra_turn_counts_as_a_new_round():
    assert count_rounds([1, 2, 2, 3, 4], 4) == 2


def test_no_turns_means_no_rounds():
    assert count_rounds([], 4) == 0
