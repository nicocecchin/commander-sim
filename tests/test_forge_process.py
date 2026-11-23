import sys
import threading
from pathlib import Path

import pytest

from commander_sim.forge import invoke
from commander_sim.forge.invoke import SimCancelled, SimError, _communicate


def python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def communicate(code: str, tmp_path: Path, timeout: float = 30, cancel=None):
    return _communicate(python(code), tmp_path, {}, timeout, cancel or threading.Event())


def test_returns_stdout(tmp_path: Path):
    stdout, _ = communicate("print('hi')", tmp_path)
    assert stdout.strip() == "hi"


def test_nonzero_exit_raises_with_stderr_tail(tmp_path: Path):
    with pytest.raises(SimError, match="code 3.*boom"):
        communicate("import sys; sys.stderr.write('boom'); sys.exit(3)", tmp_path)


def test_hard_timeout_kills_the_process(tmp_path: Path):
    with pytest.raises(SimError, match="hard timeout"):
        communicate("import time; time.sleep(60)", tmp_path, timeout=1)


def test_cancel_kills_the_process(tmp_path: Path):
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    with pytest.raises(SimCancelled):
        communicate("import time; time.sleep(60)", tmp_path, cancel=cancel)


def test_run_sim_rejects_missing_games(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "forge-gui-desktop-1-jar-with-dependencies.jar").touch()
    monkeypatch.setattr(invoke, "_communicate", lambda *a, **k: ("Simulation mode\n", ""))
    request = invoke.SimRequest(deck_dir=tmp_path, decks=("a.dck",), games=2)
    with pytest.raises(SimError, match="Expected 2"):
        invoke.run_sim(tmp_path, request, tmp_path / "home")
