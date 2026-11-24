import dataclasses
from pathlib import Path

import pytest
from typer.testing import CliRunner

from commander_sim.cli import app
from commander_sim.config import JobSpec, portable_job_json
from commander_sim.forge.output import GameResult, Outcome
from commander_sim.report.build import build_report_data
from commander_sim.report.render import render_report, write_report
from commander_sim.storage.load import LoadedResults
from commander_sim.storage.results import ResultStore, RunInfo, TaskFailure, TaskRecord
from tests.game_factory import FIELD, games_against_field, make_game

POD = ("a", "b", "c", "d")


def job_json(matchup: dict) -> str:
    spec = JobSpec.model_validate(
        {"name": "job", "decks_dir": ".", "matchup": matchup, "games": 8, "games_per_task": 4}
    )
    return portable_job_json(spec)


def run_info(job: str, weak=None) -> RunInfo:
    return RunInfo("run", "job", "2.0.16", "2026-11-24T10:00:00", job, {"a": "h-a"}, weak or {})


POD_JOB = job_json({"kind": "pod", "decks": ["a", "b", "c", "d"]})
AB_JOB = job_json({"kind": "ab", "variants": ["a", "b"], "field": list(FIELD)})


def render(games, job=POD_JOB, failures=(), weak=None, owners=None) -> str:
    results = LoadedResults([run_info(job, weak)], list(games), list(failures))
    return render_report(build_report_data(results, owners or {}, "2026-11-24 10:00", bootstrap=5))


def test_report_states_the_disclaimer_and_shows_decks_with_owners():
    games = [make_game(POD, 1), make_game(POD, 2), make_game(POD, None)]
    html = render(games, owners={"a": "Player A"})
    assert "piloted by the Forge AI" in html
    assert "a (Player A)" in html
    assert "<svg" in html
    assert "timed out" in html


def test_odd_deck_names_cannot_break_the_page():
    games = [make_game(("<script>alert(1)</script>", "b", "c", "d"), 1)]
    html = render(games)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_ab_section_only_appears_for_ab_runs():
    ab_games = games_against_field("a", 300, 1200) + games_against_field("b", 360, 1200)
    assert "A/B: a vs b" in render(ab_games, job=AB_JOB)
    assert "A/B:" not in render([make_game(POD, 1)])


def test_ab_section_repeats_the_comparison_warnings():
    ab_games = games_against_field("a", 10, 40) + games_against_field("b", 12, 40)
    html = render(ab_games, job=AB_JOB)
    assert "Too few games" in html


def test_failed_tasks_changed_decks_and_ai_weak_cards_are_reported():
    games = [make_game(POD, 1, hashes={"a": "v1"}), make_game(POD, 1, hashes={"a": "v2"})]
    html = render(
        games,
        failures=[TaskFailure("run", 3, "jvm died")],
        weak={"a": ["Toxic Deluge"]},
    )
    assert "jvm died" in html
    assert "2 different card lists" in html
    assert "Toxic Deluge" in html


def test_clean_run_says_so():
    assert "No crashed tasks" in render([make_game(POD, 1)])


def test_seat_balance_grid_counts_games_per_seat():
    games = [make_game(POD, 1), make_game(("b", "a", "c", "d"), 1)]
    html = render(games)
    assert "Seat 1" in html and "Seat 4" in html


def test_a_run_with_only_crashes_and_timeouts_still_renders():
    games = [
        make_game(POD, None, outcome=Outcome.CRASH),
        dataclasses.replace(make_game(POD, None), duration_ms=None, turns=None, rounds=None),
    ]
    html = render(games)
    assert "<html" in html
    assert "crashed" in html


def test_unreadable_job_is_shown_as_unknown():
    html = render([make_game(POD, 1)], job="not json")
    assert "unknown" in html


def test_write_report_creates_the_file(tmp_path: Path):
    results = LoadedResults([run_info(POD_JOB)], [make_game(POD, 1)], [])
    out = write_report(results, {}, tmp_path / "sub" / "r.html", bootstrap=5)
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "r.sqlite"
    store = ResultStore(path)
    run_id = store.init_run("job", POD_JOB, "2.0.16", {d: f"h-{d}" for d in POD}, {})
    results = (
        GameResult(1, Outcome.WIN, 2, 20, 5, 60_000),
        GameResult(2, Outcome.WIN, 1, 24, 6, 90_000),
    )
    hashes = tuple(f"h-{d}" for d in POD)
    store.save_task(TaskRecord(0, 1, POD, hashes, results, attempts=1), run_id)
    store.close()
    return path


def test_report_command_writes_html_from_a_database(tmp_path: Path, database: Path):
    out = tmp_path / "out.html"
    result = CliRunner().invoke(
        app,
        [
            "report",
            str(database),
            "--out",
            str(out),
            "--bootstrap",
            "5",
            "--playgroup",
            str(tmp_path / "none.yaml"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "2 games" in out.read_text(encoding="utf-8")


def test_report_command_rejects_missing_database(tmp_path: Path):
    result = CliRunner().invoke(app, ["report", str(tmp_path / "missing.sqlite")])
    assert result.exit_code != 0
