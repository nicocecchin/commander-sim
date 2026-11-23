from pathlib import Path

import pytest
from pydantic import ValidationError

from commander_sim.config import ABMatchup, load_job

JOB = """
name: demo
decks_dir: decks
matchup: {kind: pod, decks: [a.dck, b.dck, c.dck, d.dck]}
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
    assert spec.deck_files == ("a.dck", "b.dck", "c.dck", "d.dck")


def test_unknown_field_is_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        load_job(write(tmp_path, JOB + "gamez: 3\n"))


def test_duplicate_deck_in_pod_is_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        load_job(write(tmp_path, JOB.replace("b.dck", "a.dck")))


def test_ab_job_lists_variants_then_field(tmp_path: Path):
    text = JOB.replace(
        "{kind: pod, decks: [a.dck, b.dck, c.dck, d.dck]}",
        "{kind: ab, variants: [a1.dck, a2.dck], field: [x.dck, y.dck, z.dck]}",
    )
    spec = load_job(write(tmp_path, text))
    assert isinstance(spec.matchup, ABMatchup)
    assert spec.deck_files == ("a1.dck", "a2.dck", "x.dck", "y.dck", "z.dck")


def test_ab_variant_cannot_also_be_in_the_field(tmp_path: Path):
    text = JOB.replace(
        "{kind: pod, decks: [a.dck, b.dck, c.dck, d.dck]}",
        "{kind: ab, variants: [a1.dck, a2.dck], field: [a1.dck, y.dck, z.dck]}",
    )
    with pytest.raises(ValidationError):
        load_job(write(tmp_path, text))


def test_ab_needs_an_even_game_count(tmp_path: Path):
    text = JOB.replace(
        "{kind: pod, decks: [a.dck, b.dck, c.dck, d.dck]}",
        "{kind: ab, variants: [a1.dck, a2.dck], field: [x.dck, y.dck, z.dck]}",
    ).replace("games: 8", "games: 9")
    with pytest.raises(ValidationError):
        load_job(write(tmp_path, text))
