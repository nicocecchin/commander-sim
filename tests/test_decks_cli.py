from pathlib import Path

import pytest
from typer.testing import CliRunner

from commander_sim.cli import app
from commander_sim.decks.dck_format import write_dck
from commander_sim.decks.model import Deck, DeckCard
from commander_sim.forge.install import PINNED_RELEASE
from tests.card_scripts import write_forge_dir

runner = CliRunner()


@pytest.fixture
def vendor_dir(tmp_path: Path) -> Path:
    vendor = tmp_path / "vendor"
    write_forge_dir(vendor / PINNED_RELEASE.version, "forest", "thrasios", "sol_ring")
    return vendor


def valid_deck(name: str = "Good") -> Deck:
    return Deck(name, (DeckCard("Thrasios, Triton Hero"),), (DeckCard("Forest", 99),))


def invalid_deck(name: str = "Bad") -> Deck:
    return Deck(name, (DeckCard("Thrasios, Triton Hero"),), (DeckCard("Forest", 10),))


def test_validate_exit_code_follows_errors(tmp_path: Path, vendor_dir: Path):
    write_dck(valid_deck(), tmp_path / "good.dck")
    ok = runner.invoke(app, ["decks", "validate", str(tmp_path), "--vendor-dir", str(vendor_dir)])
    assert ok.exit_code == 0
    assert "Good: OK" in ok.output

    write_dck(invalid_deck(), tmp_path / "bad.dck")
    bad = runner.invoke(app, ["decks", "validate", str(tmp_path), "--vendor-dir", str(vendor_dir)])
    assert bad.exit_code == 1
    assert "expected 100" in bad.output


def test_import_writes_dck_and_keeps_the_source(tmp_path: Path, vendor_dir: Path):
    source = tmp_path / "list.txt"
    source.write_text("1 Thrasios, Triton Hero [Commander{top}]\n99 Forest\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        ["decks", "import", str(source), "--name", "My Deck", "--out-dir", str(out_dir)]
        + ["--vendor-dir", str(vendor_dir)],
    )
    assert result.exit_code == 0, result.output
    assert (out_dir / "my-deck.dck").is_file()
    assert (out_dir / "my-deck.source.txt").read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )


def test_import_refuses_invalid_deck_unless_allowed(tmp_path: Path, vendor_dir: Path):
    source = tmp_path / "list.txt"
    source.write_text("1 Thrasios, Triton Hero [Commander{top}]\n5 Forest\n", encoding="utf-8")
    args = ["decks", "import", str(source), "--name", "Short", "--out-dir", str(tmp_path / "o")]
    args += ["--vendor-dir", str(vendor_dir)]
    refused = runner.invoke(app, args)
    assert refused.exit_code == 1
    assert not (tmp_path / "o" / "short.dck").exists()
    assert runner.invoke(app, [*args, "--allow-invalid"]).exit_code == 0
    assert (tmp_path / "o" / "short.dck").is_file()


def test_run_refuses_invalid_decks_before_launching_forge(tmp_path: Path, vendor_dir: Path):
    write_dck(valid_deck("A"), tmp_path / "a.dck")
    write_dck(invalid_deck("B"), tmp_path / "b.dck")
    job = tmp_path / "job.yaml"
    job.write_text(
        "name: j\ndecks_dir: .\nmatchup: {kind: pod, decks: [a.dck, b.dck]}\ngames: 2\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["run", str(job), "--runs-dir", str(tmp_path / "runs"), "--vendor-dir", str(vendor_dir)],
    )
    assert result.exit_code == 1
    assert "Refusing to run invalid decks" in result.output
    assert not (tmp_path / "runs").exists()
