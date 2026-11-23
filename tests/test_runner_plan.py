from collections import Counter
from itertools import combinations

from commander_sim.config import JobSpec
from commander_sim.runner.plan import balance_warnings, derive_seed, plan_tasks

POD = ("a", "b", "c", "d")


def make_spec(matchup: dict, games: int = 96, **overrides) -> JobSpec:
    fields = {"name": "t", "decks_dir": ".", "games_per_task": 4, "seed": 3}
    return JobSpec.model_validate({**fields, "matchup": matchup, "games": games, **overrides})


def pod_spec(games: int = 96) -> JobSpec:
    return make_spec({"kind": "pod", "decks": list(POD)}, games)


def seat_counts(tasks) -> Counter:
    counts: Counter = Counter()
    for task in tasks:
        for seat, deck in enumerate(task.seats, start=1):
            counts[(deck, seat)] += task.games
    return counts


def test_pod_every_deck_plays_every_seat_equally_often():
    counts = seat_counts(plan_tasks(pod_spec()))
    assert len(counts) == 16
    assert set(counts.values()) == {24}


def test_task_games_sum_to_total_with_short_last_task():
    assert [t.games for t in plan_tasks(pod_spec(games=10))] == [4, 4, 2]


def test_plan_is_deterministic_and_seeds_differ_per_scenario():
    first, second = plan_tasks(pod_spec()), plan_tasks(pod_spec())
    assert first == second
    assert len({t.seed for t in first}) == len(first)
    assert derive_seed(3, 0) != derive_seed(4, 0)


def test_pod_cycles_use_different_neighbours():
    tasks = plan_tasks(pod_spec(games=96))
    cycles = {tuple(sorted(zip(t.seats, t.seats[1:] + t.seats[:1], strict=True))) for t in tasks}
    assert len(cycles) > 1


def test_ab_variants_face_identical_opponents_seats_and_seeds():
    field = ["x", "y", "z", "w", "v"]
    spec = make_spec({"kind": "ab", "variants": ["a1", "a2"], "field": field}, games=320)
    tasks = plan_tasks(spec)
    assert len(tasks) % 2 == 0
    for first, second in zip(tasks[::2], tasks[1::2], strict=True):
        assert first.seed == second.seed
        assert first.games == second.games
        swapped = tuple("a1" if d == "a2" else d for d in second.seats)
        assert swapped == first.seats
        assert "a2" in second.seats and "a1" in first.seats


def test_ab_is_balanced_over_seats_and_opponent_sets():
    field = ["x", "y", "z", "w", "v"]
    games = 2 * 4 * 4 * len(list(combinations(field, 3)))  # variants x rotations x gpt x sets
    spec = make_spec({"kind": "ab", "variants": ["a1", "a2"], "field": field}, games=games)
    counts = seat_counts(plan_tasks(spec))
    for variant in ("a1", "a2"):
        assert {counts[(variant, seat)] for seat in range(1, 5)} == {games // 2 // 4}
    assert balance_warnings(spec) == []
    opponents = Counter(
        frozenset(d for d in t.seats if d not in ("a1", "a2")) for t in plan_tasks(spec)
    )
    assert len(set(opponents.values())) == 1 and len(opponents) == 10


def test_league_plays_every_combination_with_all_rotations():
    decks = ["a", "b", "c", "d", "e"]
    spec = make_spec({"kind": "league", "decks": decks}, games=5 * 4 * 4)
    tasks = plan_tasks(spec)
    pods = Counter(frozenset(t.seats) for t in tasks)
    assert len(pods) == 5 and set(pods.values()) == {4}
    counts = seat_counts(tasks)
    assert set(counts.values()) == {16 // 4 * 4 * 4 // 4}  # 4 pods per deck x 4 games
    assert balance_warnings(spec) == []


def test_balance_warnings_name_the_cycle():
    assert balance_warnings(pod_spec(96)) == []
    assert "not a multiple of 16" in balance_warnings(pod_spec(100))[0]
