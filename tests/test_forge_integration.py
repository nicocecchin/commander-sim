"""Slow test that runs real Forge. Run with: uv run pytest -m integration"""

from pathlib import Path

import pytest

from commander_sim.forge.install import PINNED_RELEASE
from commander_sim.forge.invoke import SimRequest, run_sim
from commander_sim.forge.output import Outcome

FORGE_DIR = Path("vendor") / "forge" / PINNED_RELEASE.version
STARTER_DECKS = FORGE_DIR / "res" / "adventure" / "common" / "decks" / "starter" / "commander"


@pytest.mark.integration
def test_seeded_game_is_reproducible(tmp_path: Path):
    request = SimRequest(
        deck_dir=STARTER_DECKS,
        decks=("black_01.dck", "blue_01.dck", "green_01.dck", "red_01.dck"),
        seed=42,
        game_timeout_seconds=1800,
    )
    first = run_sim(FORGE_DIR, request, tmp_path / "home1")
    second = run_sim(FORGE_DIR, request, tmp_path / "home2")

    assert first.seed == 42
    assert first.games[0].outcome is Outcome.WIN
    assert [(g.outcome, g.winner_seat, g.turns) for g in first.games] == [
        (g.outcome, g.winner_seat, g.turns) for g in second.games
    ]
