"""Build and run ``forge sim`` commands."""

import os
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from commander_sim.forge.output import SimOutput, parse_sim_output

DEFAULT_HEAP_MB = 1536
DEFAULT_TIMEOUT_SECONDS = 3600
STARTUP_MARGIN_SECONDS = 300
_POLL_SECONDS = 0.5
_STDERR_TAIL_CHARS = 500


class SimError(RuntimeError):
    """A Forge launch failed (non-zero exit, hard timeout or unusable output)."""


class SimCancelled(Exception):
    """The launch was stopped because the caller asked to cancel."""


@dataclass(frozen=True)
class SimRequest:
    """One `sim` invocation. Deck order is seat order (first deck is seat 1)."""

    deck_dir: Path
    decks: tuple[str, ...]
    games: int = 1
    seed: int | None = None
    game_timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    heap_mb: int = DEFAULT_HEAP_MB

    @property
    def hard_timeout_seconds(self) -> int:
        """Wall-clock limit after which the whole JVM is killed as hung."""
        return self.games * self.game_timeout_seconds + STARTUP_MARGIN_SECONDS


def find_forge_jar(forge_dir: Path) -> Path:
    jars = sorted(forge_dir.glob("forge-gui-desktop-*-jar-with-dependencies.jar"))
    if not jars:
        raise FileNotFoundError(f"No Forge desktop jar in {forge_dir}; run `forge setup`")
    return jars[-1]


def build_command(forge_dir: Path, request: SimRequest, user_home: Path) -> list[str]:
    """Return the argument list for a sim run.

    `user_home` becomes the JVM's ``user.home``, which is where Forge keeps its user data and
    cache, so distinct values isolate parallel runs from each other.
    """
    command = [
        "java",
        f"-Xmx{request.heap_mb}m",
        f"-Duser.home={user_home}",
        "-jar",
        find_forge_jar(forge_dir).name,
        "sim",
        "-d",
        *request.decks,
        "-D",
        str(request.deck_dir.resolve()),
        "-f",
        "Commander",
        "-n",
        str(request.games),
        "-c",
        str(request.game_timeout_seconds),
    ]
    if request.seed is not None:
        command += ["-s", str(request.seed)]
    return command


def isolation_env(
    user_home: Path, base_env: Mapping[str, str] | None = None, platform: str = sys.platform
) -> dict[str, str]:
    """Environment for the JVM. On Windows Forge derives its data dirs from APPDATA variables."""
    env = dict(os.environ if base_env is None else base_env)
    if platform == "win32":
        env["APPDATA"] = str(user_home / "AppData" / "Roaming")
        env["LOCALAPPDATA"] = str(user_home / "AppData" / "Local")
    return env


def _communicate(
    command: list[str],
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: float,
    cancel: threading.Event,
) -> tuple[str, str]:
    """Run a process to completion, killing it on timeout or cancellation."""
    deadline = time.monotonic() + timeout_seconds
    with subprocess.Popen(
        command,
        cwd=cwd,
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    ) as process:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=_POLL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                if cancel.is_set():
                    process.kill()
                    raise SimCancelled() from None
                if time.monotonic() > deadline:
                    process.kill()
                    raise SimError(
                        f"Forge exceeded the {timeout_seconds:.0f}s hard timeout"
                    ) from None
        if process.returncode != 0:
            tail = stderr.strip()[-_STDERR_TAIL_CHARS:]
            raise SimError(f"Forge exited with code {process.returncode}: {tail}")
    return stdout, stderr


def run_sim(
    forge_dir: Path,
    request: SimRequest,
    user_home: Path,
    cancel: threading.Event | None = None,
) -> SimOutput:
    """Run Forge and parse its output. Forge must run with its own directory as cwd.

    Raises SimError if the launch fails or yields fewer games than requested, and SimCancelled
    if `cancel` is set while it runs.
    """
    user_home.mkdir(parents=True, exist_ok=True)
    stdout, _ = _communicate(
        build_command(forge_dir, request, user_home),
        cwd=forge_dir,
        env=isolation_env(user_home),
        timeout_seconds=request.hard_timeout_seconds,
        cancel=cancel or threading.Event(),
    )
    output = parse_sim_output(stdout)
    if len(output.games) != request.games:
        raise SimError(f"Expected {request.games} game results, parsed {len(output.games)}")
    return output
