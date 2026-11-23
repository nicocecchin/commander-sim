from pathlib import Path

import pytest

from commander_sim.forge.invoke import SimRequest, build_command, find_forge_jar, isolation_env

JAR = "forge-gui-desktop-9.9.9-jar-with-dependencies.jar"


@pytest.fixture
def forge_dir(tmp_path: Path) -> Path:
    (tmp_path / JAR).touch()
    return tmp_path


def test_find_forge_jar(forge_dir: Path):
    assert find_forge_jar(forge_dir).name == JAR


def test_find_forge_jar_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        find_forge_jar(tmp_path)


def test_build_command_orders_decks_as_seats_and_adds_seed(forge_dir: Path, tmp_path: Path):
    request = SimRequest(deck_dir=tmp_path, decks=("a.dck", "b.dck"), games=3, seed=7)
    command = build_command(forge_dir, request, user_home=tmp_path / "home")
    deck_args = command[command.index("-d") + 1 : command.index("-D")]
    assert deck_args == ["a.dck", "b.dck"]
    assert command[command.index("-s") + 1] == "7"
    assert command[command.index("-n") + 1] == "3"
    assert f"-Duser.home={tmp_path / 'home'}" in command
    assert "-q" not in command


def test_build_command_omits_seed_when_unset(forge_dir: Path, tmp_path: Path):
    request = SimRequest(deck_dir=tmp_path, decks=("a.dck",))
    assert "-s" not in build_command(forge_dir, request, user_home=tmp_path)


def test_hard_timeout_scales_with_games(tmp_path: Path):
    one = SimRequest(deck_dir=tmp_path, decks=("a.dck",), games=1, game_timeout_seconds=100)
    four = SimRequest(deck_dir=tmp_path, decks=("a.dck",), games=4, game_timeout_seconds=100)
    assert four.hard_timeout_seconds - one.hard_timeout_seconds == 300


def test_isolation_env_only_redirects_appdata_on_windows(tmp_path: Path):
    base = {"PATH": "x"}
    assert isolation_env(tmp_path, base, platform="linux") == base
    windows = isolation_env(tmp_path, base, platform="win32")
    assert windows["APPDATA"].startswith(str(tmp_path))
    assert windows["LOCALAPPDATA"].startswith(str(tmp_path))
