"""Slow end-to-end test: real Forge, real workers, real SQLite."""

import threading
from pathlib import Path

import pytest

from commander_sim.config import JobSpec
from commander_sim.forge.install import PINNED_RELEASE
from commander_sim.forge.invoke import SimRequest, run_sim
from commander_sim.forge.output import Outcome, SimOutput
from commander_sim.runner.executor import run_job
from commander_sim.storage.results import ResultStore

FORGE_DIR = Path("vendor") / "forge" / PINNED_RELEASE.version
SAMPLE_DECKS = Path("decks") / "sample"


@pytest.mark.integration
def test_two_parallel_tasks_are_stored(tmp_path: Path):
    spec = JobSpec(
        name="it",
        decks_dir=SAMPLE_DECKS,
        matchup={
            "kind": "pod",
            "decks": ("black_01.dck", "blue_01.dck", "green_01.dck", "red_01.dck"),
        },
        games=2,
        games_per_task=1,
        seed=5,
    )

    def simulate(request: SimRequest, home: Path, cancel: threading.Event) -> SimOutput:
        return run_sim(FORGE_DIR, request, home, cancel)

    store = ResultStore(tmp_path / "results.sqlite")
    hashes = {deck: f"hash-{deck}" for deck in spec.deck_files}
    run_id = store.init_run(spec.name, spec.model_dump_json(), PINNED_RELEASE.version, hashes, {})
    run_job(spec, store, run_id, hashes, tmp_path, simulate, workers=2)

    assert store.completed_tasks(run_id) == {0, 1}
    assert store.outcome_counts().get(Outcome.CRASH, 0) == 0
    assert sum(store.outcome_counts().values()) == 2
    for game in store.read_games():
        assert game.turns and game.rounds and game.rounds <= game.turns
    assert len(list((tmp_path / "workers").glob("*/home/.forge"))) == 2
    store.close()
