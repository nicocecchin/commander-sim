from pathlib import Path

import pytest

from commander_sim.forge.output import GameResult, Outcome
from commander_sim.storage.results import ResultStore, RunMismatchError, TaskRecord

SEATS = ("a.dck", "b.dck", "c.dck", "d.dck")


@pytest.fixture
def store(tmp_path: Path):
    store = ResultStore(tmp_path / "r.sqlite")
    yield store
    store.close()


def win(number: int, seat: int) -> GameResult:
    return GameResult(number, Outcome.WIN, seat, turns=30, duration_ms=1000)


def record(index: int = 0, games=None, error: str | None = None) -> TaskRecord:
    games = games if games is not None else (win(1, 2), win(2, 4))
    return TaskRecord(index, seed=9, seat_decks=SEATS, games=games, attempts=1, error=error)


def test_init_run_is_stable_on_resume_and_rejects_other_jobs(store: ResultStore):
    run_id = store.init_run('{"a": 1}', "2.0.16")
    assert store.init_run('{"a": 1}', "2.0.16") == run_id
    with pytest.raises(RunMismatchError):
        store.init_run('{"a": 2}', "2.0.16")
    with pytest.raises(RunMismatchError):
        store.init_run('{"a": 1}', "2.0.17")


def test_saved_task_is_complete_and_winners_map_to_decks(store: ResultStore):
    run_id = store.init_run("{}", "2.0.16")
    store.save_task(record(0), run_id, "2.0.16")
    assert store.completed_tasks() == {0}
    assert store.outcome_counts() == {Outcome.WIN: 2}
    assert store.winner_counts() == {"b.dck": 1, "d.dck": 1}


def test_failed_task_stores_crashes_and_is_replaced_by_a_retry(store: ResultStore):
    run_id = store.init_run("{}", "2.0.16")
    crashes = (GameResult(1, Outcome.CRASH, None, None, None),)
    store.save_task(record(0, crashes, error="boom"), run_id, "2.0.16")
    assert store.completed_tasks() == set()
    assert store.outcome_counts() == {Outcome.CRASH: 1}
    assert store.failed_errors() == [(0, "boom")]

    store.save_task(record(0, (win(1, 1),)), run_id, "2.0.16")
    assert store.completed_tasks() == {0}
    assert store.outcome_counts() == {Outcome.WIN: 1}
    assert store.failed_errors() == []


def test_timeouts_are_counted_separately_from_wins(store: ResultStore):
    run_id = store.init_run("{}", "2.0.16")
    timeout = GameResult(1, Outcome.TIMEOUT, None, turns=6, duration_ms=10)
    store.save_task(record(0, (timeout, win(2, 1))), run_id, "2.0.16")
    assert store.outcome_counts() == {Outcome.TIMEOUT: 1, Outcome.WIN: 1}
    assert store.winner_counts() == {"a.dck": 1}
