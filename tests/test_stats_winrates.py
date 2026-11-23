from commander_sim.forge.output import Outcome
from commander_sim.stats.winrates import deck_stats, deck_versions, seat_stats
from tests.game_factory import make_game

POD = ("a", "b", "c", "d")


def by_deck(games):
    return {s.deck: s for s in deck_stats(games)}


def test_wins_and_winrate_per_deck():
    games = [make_game(POD, 1), make_game(POD, 1), make_game(POD, 2), make_game(POD, 4)]
    stats = by_deck(games)
    assert (stats["a"].wins, stats["a"].decided, stats["a"].winrate) == (2, 4, 0.5)
    assert stats["c"].wins == 0
    low, high = stats["a"].interval
    assert low < 0.5 < high


def test_timeouts_are_reported_separately_and_not_counted_as_losses():
    games = [make_game(POD, 1), make_game(POD, None)]
    a = by_deck(games)["a"]
    assert (a.appearances, a.timeouts, a.decided, a.winrate) == (2, 1, 1, 1.0)
    assert a.timeout_rate == 0.5


def test_crashes_count_only_as_crashes():
    games = [make_game(POD, 1), make_game(POD, None, outcome=Outcome.CRASH)]
    a = by_deck(games)["a"]
    assert (a.appearances, a.decided, a.crashes) == (1, 1, 1)


def test_results_are_sorted_best_first():
    games = [make_game(POD, 3), make_game(POD, 3), make_game(POD, 1)]
    assert [s.deck for s in deck_stats(games)][:2] == ["c", "a"]


def test_seat_winrates_use_only_decided_games():
    games = [make_game(POD, 1), make_game(POD, 1), make_game(POD, 2), make_game(POD, None)]
    seats = {s.seat: s for s in seat_stats(games)}
    assert (seats[1].wins, seats[1].decided) == (2, 3)
    assert seats[3].wins == 0


def test_deck_versions_flags_changed_card_lists():
    games = [make_game(POD, 1, hashes={"a": "v1"}), make_game(POD, 1, hashes={"a": "v2"})]
    assert deck_versions(games) == {"a": {"v1", "v2"}}
    assert deck_versions([make_game(POD, 1)]) == {}


def test_win_length_is_reported_as_turns_and_rounds():
    games = [
        make_game(POD, 1),
        make_game(POD, 1),
        make_game(POD, 2),
    ]  # each lasted 20 turns, 5 rounds
    a = by_deck(games)["a"]
    assert (a.mean_win_turn, a.mean_win_rounds) == (20, 5.0)
    assert by_deck(games)["c"].mean_win_turn is None
