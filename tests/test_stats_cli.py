from pathlib import Path

import pytest
from typer.testing import CliRunner

from commander_sim.cli import app
from commander_sim.forge.output import GameResult, Outcome
from commander_sim.storage.results import ResultStore, TaskRecord

runner = CliRunner()
DECKS = ("a.dck", "b.dck", "c.dck", "d.dck")
HASHES = {deck: f"h-{deck}" for deck in DECKS}


def make_db(path: Path, name: str = "job", wins_for_seat_one: int = 6, games: int = 8) -> Path:
    store = ResultStore(path)
    run_id = store.init_run(name, name, "2.0.16", HASHES, {"a.dck": ["Toxic Deluge"]})
    results = tuple(
        GameResult(n, Outcome.WIN, 1 if n <= wins_for_seat_one else 2, 20, 5, 1000)
        for n in range(1, games + 1)
    )
    record = TaskRecord(0, 1, DECKS, tuple(HASHES.values()), results, attempts=1)
    store.save_task(record, run_id)
    store.close()
    return path


def invoke(*args: str):
    return runner.invoke(app, [str(a) for a in args])


def test_stats_shows_tables_ai_weakness_and_the_forge_ai_disclaimer(tmp_path: Path):
    db = make_db(tmp_path / "r.sqlite")
    result = invoke("stats", db, "--bootstrap", 10, "--playgroup", tmp_path / "none.yaml")
    assert result.exit_code == 0, result.output
    assert "a" in result.output and "75.0%" in result.output
    assert "Toxic Deluge" in result.output
    assert "piloted by the Forge AI" in result.output
    assert "20.0 / 5.0" in result.output
    assert "one pass around the table" in result.output


def test_stats_uses_owner_names_from_the_playgroup_file(tmp_path: Path):
    db = make_db(tmp_path / "r.sqlite")
    group = tmp_path / "group.yaml"
    group.write_text("players:\n  Player A: [a.dck]\n", encoding="utf-8")
    result = invoke("stats", db, "--bootstrap", 10, "--playgroup", group)
    assert "a (Player A)" in result.output


def test_compare_warns_when_the_sample_is_too_small(tmp_path: Path):
    db = make_db(tmp_path / "r.sqlite")
    result = invoke("compare", db, "--a", "a.dck", "--b", "b.dck")
    assert result.exit_code == 0, result.output
    assert "Too few games" in result.output
    assert "both decks at the table" in result.output


def test_compare_unknown_deck_is_an_error(tmp_path: Path):
    db = make_db(tmp_path / "r.sqlite")
    assert invoke("compare", db, "--a", "a.dck", "--b", "zzz.dck").exit_code != 0


def test_merge_combines_databases_and_refuses_repeats(tmp_path: Path):
    first = make_db(tmp_path / "1.sqlite", name="one")
    second = make_db(tmp_path / "2.sqlite", name="two")
    merged = tmp_path / "all.sqlite"
    assert invoke("merge", merged, first, second).exit_code == 0
    store = ResultStore(merged)
    assert len(store.read_runs()) == 2
    assert len(store.read_games()) == 16
    store.close()

    assert invoke("merge", tmp_path / "again.sqlite", merged, first).exit_code != 0
    assert not (tmp_path / "again.sqlite").exists()
    assert invoke("merge", merged, first).exit_code != 0


def test_stats_refuses_the_same_run_twice(tmp_path: Path):
    db = make_db(tmp_path / "r.sqlite")
    result = invoke("stats", db, db)
    assert result.exit_code != 0


@pytest.mark.parametrize("command", ["stats", "compare"])
def test_missing_database_is_reported(tmp_path: Path, command: str):
    extra = ["--a", "x", "--b", "y"] if command == "compare" else []
    assert invoke(command, tmp_path / "missing.sqlite", *extra).exit_code != 0
