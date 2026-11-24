import os
import signal
import sqlite3
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from commander_sim.cli import app
from commander_sim.config import (
    JobSpec,
    WorkerSettings,
    job_from_portable_json,
    portable_job_json,
)
from commander_sim.forge.output import GameResult, Outcome
from commander_sim.runner.signals import stop_on_sigterm
from commander_sim.storage.results import ResultStore, TaskRecord, snapshot_database

POD = ("a.dck", "b.dck", "c.dck", "d.dck")
HASHES = {d: f"h-{d}" for d in POD}


def spec(decks_dir: str = ".", workers: WorkerSettings | None = None) -> JobSpec:
    return JobSpec(
        name="job",
        decks_dir=decks_dir,
        matchup={"kind": "pod", "decks": POD},
        games=8,
        workers=workers or WorkerSettings(),
    )


def test_portable_job_ignores_deck_folder_and_worker_limits():
    here = portable_job_json(spec("/home/me/decks"))
    there = portable_job_json(spec("/srv/bundle/decks", WorkerSettings(max=12)))
    assert here == there
    assert "decks_dir" not in here and "workers" not in here


def test_portable_job_round_trips():
    original = spec("/somewhere")
    restored = job_from_portable_json(portable_job_json(original))
    assert restored.matchup == original.matchup
    assert restored.games == original.games


def test_invalid_stored_job_is_a_value_error():
    with pytest.raises(ValueError):
        job_from_portable_json("not json")


def test_run_folder_moved_to_another_machine_still_resumes(tmp_path: Path):
    store = ResultStore(tmp_path / "r.sqlite")
    run_id = store.init_run("job", portable_job_json(spec("/laptop/decks")), "2.0.16", HASHES, {})
    moved = portable_job_json(spec("/runbox/decks", WorkerSettings(max=12)))
    assert store.init_run("job", moved, "2.0.16", HASHES, {}) == run_id
    store.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_sigterm_becomes_keyboard_interrupt_and_handler_is_restored():
    before = signal.getsignal(signal.SIGTERM)
    with pytest.raises(KeyboardInterrupt), stop_on_sigterm():
        os.kill(os.getpid(), signal.SIGTERM)
    assert signal.getsignal(signal.SIGTERM) == before


def save_games(store: ResultStore, run_id: str, task: int, count: int) -> None:
    games = tuple(GameResult(n, Outcome.WIN, 1, 20, 5, 1000) for n in range(1, count + 1))
    store.save_task(TaskRecord(task, 1, POD, tuple(HASHES.values()), games, attempts=1), run_id)


def test_snapshot_copies_a_database_that_is_still_open_for_writing(tmp_path: Path):
    live = ResultStore(tmp_path / "live.sqlite")
    run_id = live.init_run("job", portable_job_json(spec()), "2.0.16", HASHES, {})
    save_games(live, run_id, 0, 4)
    snapshot_database(tmp_path / "live.sqlite", tmp_path / "copy.sqlite")
    save_games(live, run_id, 1, 4)
    live.close()

    copy = ResultStore(tmp_path / "copy.sqlite")
    assert len(copy.read_games()) == 4
    copy.close()
    with sqlite3.connect(tmp_path / "copy.sqlite") as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_progress_command_reports_done_out_of_total(tmp_path: Path):
    store = ResultStore(tmp_path / "r.sqlite")
    run_id = store.init_run("job", portable_job_json(spec()), "2.0.16", HASHES, {})
    save_games(store, run_id, 0, 4)
    store.close()
    result = CliRunner().invoke(app, ["progress", str(tmp_path / "r.sqlite")])
    assert result.exit_code == 0, result.output
    assert "job: 4/8 games, win=4 timeout=0 crash=0" in result.output


def test_snapshot_command_refuses_a_missing_database(tmp_path: Path):
    result = CliRunner().invoke(app, ["snapshot", str(tmp_path / "x.sqlite"), str(tmp_path / "y")])
    assert result.exit_code != 0
