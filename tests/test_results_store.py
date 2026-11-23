import sqlite3
from pathlib import Path

import pytest

from commander_sim.forge.output import GameResult, Outcome
from commander_sim.storage.results import (
    ResultStore,
    RunMismatchError,
    SchemaVersionError,
    TaskRecord,
)

SEATS = ("a.dck", "b.dck", "c.dck", "d.dck")
HASHES = {deck: f"h-{deck}" for deck in SEATS}
FORGE = "2.0.16"


@pytest.fixture
def store(tmp_path: Path):
    store = ResultStore(tmp_path / "r.sqlite")
    yield store
    store.close()


def init(store: ResultStore, job: str = "{}", hashes=HASHES, forge: str = FORGE) -> str:
    return store.init_run("job", job, forge, hashes, {"a.dck": ["Toxic Deluge"]})


def win(number: int, seat: int) -> GameResult:
    return GameResult(number, Outcome.WIN, seat, turns=30, rounds=8, duration_ms=1000)


def record(index: int = 0, games=None, error: str | None = None) -> TaskRecord:
    games = games if games is not None else (win(1, 2), win(2, 4))
    seat_hashes = tuple(HASHES[d] for d in SEATS)
    return TaskRecord(index, 9, SEATS, seat_hashes, games, attempts=1, error=error)


def test_init_run_is_stable_on_resume_and_rejects_changes(store: ResultStore):
    run_id = init(store)
    assert init(store) == run_id
    with pytest.raises(RunMismatchError):
        init(store, job='{"a": 2}')
    with pytest.raises(RunMismatchError):
        init(store, forge="2.0.17")
    with pytest.raises(RunMismatchError):
        init(store, hashes={**HASHES, "a.dck": "edited"})


def test_saved_games_are_read_back_with_seats_hashes_and_winner(store: ResultStore):
    run_id = init(store)
    store.save_task(record(0), run_id)
    assert store.completed_tasks(run_id) == {0}
    assert store.outcome_counts() == {Outcome.WIN: 2}
    games = store.read_games()
    assert [g.winner.deck for g in games] == ["b.dck", "d.dck"]
    assert [s.deck for s in games[0].seats] == list(SEATS)
    assert games[0].seats[0].deck_hash == "h-a.dck"
    (run,) = store.read_runs()
    assert run.ai_weak_cards == {"a.dck": ["Toxic Deluge"]}
    assert run.forge_version == FORGE


def test_failed_task_stores_crashes_and_is_replaced_by_a_retry(store: ResultStore):
    run_id = init(store)
    crashes = (GameResult(1, Outcome.CRASH, None, None, None, None),)
    store.save_task(record(0, crashes, error="boom"), run_id)
    assert store.completed_tasks(run_id) == set()
    assert store.outcome_counts() == {Outcome.CRASH: 1}
    assert store.failed_errors(run_id) == [(0, "boom")]

    store.save_task(record(0, (win(1, 1),)), run_id)
    assert store.completed_tasks(run_id) == {0}
    assert store.outcome_counts() == {Outcome.WIN: 1}
    assert store.failed_errors(run_id) == []


def test_timeouts_have_no_winner(store: ResultStore):
    run_id = init(store)
    timeout = GameResult(1, Outcome.TIMEOUT, None, turns=6, rounds=2, duration_ms=10)
    store.save_task(record(0, (timeout, win(2, 1))), run_id)
    assert store.outcome_counts() == {Outcome.TIMEOUT: 1, Outcome.WIN: 1}
    assert [g.winner for g in store.read_games()][0] is None


def test_import_runs_copies_everything_and_refuses_duplicates(tmp_path: Path):
    first, second, merged = (ResultStore(tmp_path / f"{n}.sqlite") for n in ("1", "2", "m"))
    first_id = init(first)
    first.save_task(record(0), first_id)
    second.init_run("other", "{}", FORGE, HASHES, {})
    second.save_task(record(0, (win(1, 3),)), second.read_runs()[0].run_id)

    assert merged.import_runs(first) == [first_id]
    merged.import_runs(second)
    assert len(merged.read_runs()) == 2
    assert merged.outcome_counts() == {Outcome.WIN: 3}
    assert [len(g.seats) for g in merged.read_games()] == [4, 4, 4]

    with pytest.raises(RunMismatchError):
        merged.import_runs(first)
    assert len(merged.read_games()) == 3
    for store in (first, second, merged):
        store.close()


def test_incompatible_schema_version_is_refused(tmp_path: Path):
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version = 1")
    with pytest.raises(SchemaVersionError):
        ResultStore(path)
