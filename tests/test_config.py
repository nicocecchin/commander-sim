from pathlib import Path

import pytest
from pydantic import ValidationError

from commander_sim.config import load_job

JOB = """
name: demo
decks_dir: decks
pod: [a.dck, b.dck, c.dck, d.dck]
games: 8
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "job.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_job_resolves_decks_dir_against_job_file(tmp_path: Path):
    spec = load_job(write(tmp_path, JOB))
    assert spec.decks_dir == (tmp_path / "decks").resolve()
    assert spec.games_per_task == 4


def test_unknown_field_is_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        load_job(write(tmp_path, JOB + "gamez: 3\n"))


def test_duplicate_deck_in_pod_is_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        load_job(write(tmp_path, JOB.replace("b.dck", "a.dck")))
