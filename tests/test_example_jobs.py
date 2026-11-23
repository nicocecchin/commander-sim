from pathlib import Path

import pytest

from commander_sim.config import load_job
from commander_sim.runner.plan import balance_warnings, plan_tasks

JOBS = sorted(Path("jobs").glob("*.yaml"))


@pytest.mark.parametrize("job_file", JOBS, ids=lambda p: p.name)
def test_example_job_is_valid_balanced_and_points_at_existing_decks(job_file: Path):
    spec = load_job(job_file)
    assert all((spec.decks_dir / deck).is_file() for deck in spec.deck_files)
    assert plan_tasks(spec)
    assert balance_warnings(spec) == []
