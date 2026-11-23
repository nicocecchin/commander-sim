from collections import Counter

from commander_sim.config import JobSpec
from commander_sim.runner.plan import balance_warning, derive_seed, plan_tasks


def make_spec(**overrides) -> JobSpec:
    fields = {
        "name": "t",
        "decks_dir": ".",
        "pod": ("a", "b", "c", "d"),
        "games": 96,
        "games_per_task": 4,
        "seed": 3,
    }
    return JobSpec(**{**fields, **overrides})


def test_every_deck_plays_every_seat_equally_often():
    tasks = plan_tasks(make_spec())
    counts = Counter()
    for task in tasks:
        for seat, deck in enumerate(task.seats, start=1):
            counts[(deck, seat)] += task.games
    assert set(counts.values()) == {24}
    assert len(counts) == 16


def test_task_games_sum_to_total_with_short_last_task():
    tasks = plan_tasks(make_spec(games=10))
    assert [t.games for t in tasks] == [4, 4, 2]


def test_plan_is_deterministic_and_seeds_differ_per_task():
    first, second = plan_tasks(make_spec()), plan_tasks(make_spec())
    assert first == second
    assert len({t.seed for t in first}) == len(first)
    assert derive_seed(3, 0) != derive_seed(4, 0)


def test_balance_warning():
    assert balance_warning(make_spec(games=96)) is None
    assert "not a multiple of 96" in balance_warning(make_spec(games=100))
