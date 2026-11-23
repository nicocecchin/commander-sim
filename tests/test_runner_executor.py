import threading
from pathlib import Path

import pytest

from commander_sim.config import JobSpec
from commander_sim.forge.invoke import SimCancelled, SimError, SimRequest
from commander_sim.forge.output import GameResult, Outcome, SimOutput
from commander_sim.runner.executor import run_job
from commander_sim.runner.plan import plan_tasks
from commander_sim.storage.results import ResultStore

POD = ("a.dck", "b.dck", "c.dck", "d.dck")


def make_spec(games: int = 8) -> JobSpec:
    return JobSpec(name="t", decks_dir=".", pod=POD, games=games, games_per_task=4, seed=1)


@pytest.fixture
def store(tmp_path: Path):
    store = ResultStore(tmp_path / "r.sqlite")
    yield store
    store.close()


def first_seat_wins(request: SimRequest, home: Path, cancel: threading.Event) -> SimOutput:
    games = tuple(
        GameResult(n, Outcome.WIN, 1, turns=20, duration_ms=5) for n in range(1, request.games + 1)
    )
    return SimOutput(request.seed, request.decks, games)


def run(store: ResultStore, tmp_path: Path, simulate, spec: JobSpec | None = None, workers=2):
    spec = spec or make_spec()
    run_id = store.init_run(spec.model_dump_json(), "2.0.16")
    run_job(spec, store, run_id, "2.0.16", tmp_path, simulate, workers)


def test_runs_every_game_and_records_wins_by_seat(store: ResultStore, tmp_path: Path):
    run(store, tmp_path, first_seat_wins)
    assert store.outcome_counts() == {Outcome.WIN: 8}
    assert sum(store.winner_counts().values()) == 8


def test_failed_launch_is_retried_then_succeeds(store: ResultStore, tmp_path: Path):
    calls = []

    def flaky(request, home, cancel):
        calls.append(request.seed)
        if len(calls) == 1:
            raise SimError("jvm died")
        return first_seat_wins(request, home, cancel)

    run(store, tmp_path, flaky, make_spec(games=4), workers=1)
    assert len(calls) == 2
    assert calls[0] == calls[1]  # the retry replays the same seed
    assert store.outcome_counts() == {Outcome.WIN: 4}


def test_persistent_failure_records_crashes_not_losses(store: ResultStore, tmp_path: Path):
    def broken(request, home, cancel):
        raise SimError("always")

    run(store, tmp_path, broken, make_spec(games=4), workers=1)
    assert store.outcome_counts() == {Outcome.CRASH: 4}
    assert store.completed_tasks() == set()
    assert store.failed_errors() == [(0, "always")]


def test_resume_skips_finished_tasks_and_retries_failed_ones(store: ResultStore, tmp_path: Path):
    seen: list[int] = []

    def fail_second_task(request, home, cancel):
        seen.append(request.seed)
        if len(seen) > 1:
            raise SimError("down")
        return first_seat_wins(request, home, cancel)

    run(store, tmp_path, fail_second_task, workers=1)
    assert store.completed_tasks() == {0}

    seen.clear()
    run(store, tmp_path, first_seat_wins, workers=1)
    assert store.completed_tasks() == {0, 1}
    assert store.outcome_counts() == {Outcome.WIN: 8}


def test_workers_use_separate_homes(store: ResultStore, tmp_path: Path):
    homes: set[Path] = set()
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def record_home(request, home, cancel):
        barrier.wait(timeout=10)
        with lock:
            homes.add(home)
        return first_seat_wins(request, home, cancel)

    run(store, tmp_path, record_home, workers=2)
    assert len(homes) == 2
    assert all(tmp_path in home.parents for home in homes)


def test_interrupt_cancels_running_workers_and_keeps_finished_tasks(
    store: ResultStore, tmp_path: Path
):
    cancelled = threading.Event()

    def first_task_fast_second_blocks(request, home, cancel):
        if request.seed != plan_tasks(spec)[0].seed:
            assert cancel.wait(timeout=10)
            cancelled.set()
            raise SimCancelled()
        return first_seat_wins(request, home, cancel)

    def interrupt(counts):
        raise KeyboardInterrupt

    spec = make_spec()
    run_id = store.init_run(spec.model_dump_json(), "2.0.16")
    with pytest.raises(KeyboardInterrupt):
        run_job(
            spec, store, run_id, "2.0.16", tmp_path, first_task_fast_second_blocks, 2, interrupt
        )

    assert cancelled.is_set()
    assert store.completed_tasks() == {0}
