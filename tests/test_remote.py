import json
import subprocess
from pathlib import Path

import pytest
import yaml

from commander_sim.config import JobSpec, load_job
from commander_sim.decks.dck_format import write_dck
from commander_sim.decks.model import Deck, DeckCard
from commander_sim.remote import commands
from commander_sim.remote.bundle import BundleError, write_bundle
from commander_sim.remote.commands import Remote
from commander_sim.remote.source import SourceError, clean_head_commit, write_source_archive

POD = ("a.dck", "b.dck", "c.dck", "d.dck")
REMOTE = Remote("me@pino.example.org", "commander-sim")


def make_job(tmp_path: Path) -> JobSpec:
    decks = tmp_path / "decks"
    for name in POD:
        write_dck(Deck(name, (DeckCard("Commander"),), (DeckCard("Forest", 99),)), decks / name)
    job = tmp_path / "job.yaml"
    job.write_text(
        yaml.safe_dump(
            {
                "name": "t",
                "decks_dir": "decks",
                "matchup": {"kind": "pod", "decks": list(POD)},
                "games": 8,
                "workers": {"max": 3},
            }
        ),
        encoding="utf-8",
    )
    return load_job(job)


def test_bundle_is_self_contained_and_loads_on_its_own(tmp_path: Path):
    bundle = write_bundle(make_job(tmp_path), tmp_path / "out" / "bundle", "abc123", 12)
    assert sorted(p.name for p in (bundle / "decks").iterdir()) == sorted(POD)
    reloaded = load_job(bundle / "job.yaml")
    assert reloaded.decks_dir == (bundle / "decks").resolve()
    assert reloaded.workers.max == 12
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["commit"] == "abc123"
    assert set(manifest["deck_hashes"]) == set(POD)


def test_bundle_replaces_an_old_bundle_but_nothing_else(tmp_path: Path):
    spec = make_job(tmp_path)
    write_bundle(spec, tmp_path / "bundle", "c1", 2)
    write_bundle(spec, tmp_path / "bundle", "c2", 2)
    (tmp_path / "other").mkdir()
    with pytest.raises(BundleError, match="not a bundle"):
        write_bundle(spec, tmp_path / "other", "c3", 2)


def test_bundle_refuses_missing_decks(tmp_path: Path):
    spec = make_job(tmp_path)
    (tmp_path / "decks" / "a.dck").unlink()
    with pytest.raises(BundleError, match="a.dck"):
        write_bundle(spec, tmp_path / "bundle", "c", 2)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.org")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "f.txt").write_text("one", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "c")
    return tmp_path


def test_clean_head_commit_and_archive(repo: Path, tmp_path: Path):
    commit = clean_head_commit(repo)
    assert len(commit) == 40
    archive = write_source_archive(repo, commit, tmp_path / "out" / "src.tar")
    assert archive.stat().st_size > 0


def test_uncommitted_changes_are_refused(repo: Path):
    (repo / "f.txt").write_text("two", encoding="utf-8")
    with pytest.raises(SourceError, match="Commit your changes"):
        clean_head_commit(repo)


def test_remote_paths_and_label():
    assert REMOTE.label == "pino"
    assert REMOTE.path("jobs", "t") == "commander-sim/jobs/t"
    assert REMOTE.absolute("jobs", "t") == '"$HOME"/commander-sim/jobs/t'


def test_ssh_and_scp_use_batch_mode_and_argument_lists():
    assert commands.ssh(REMOTE, "true") == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "me@pino.example.org",
        "true",
    ]
    assert commands.scp_to(REMOTE, "local", "remote/dir")[-1] == "me@pino.example.org:remote/dir"
    assert commands.scp_from(REMOTE, "x", "y")[-2:] == ["me@pino.example.org:x", "y"]


def test_start_script_resumes_and_limits_resources():
    script = commands.start_script(REMOTE, "0123456789abcdef", "precon-four", 10)
    assert "docker run -d --init" in script
    assert "--restart on-failure:5" in script
    assert "--cpus 11 --memory 20g" in script
    assert '-v "$HOME"/commander-sim/jobs/precon-four:/work' in script
    assert "commander-sim:0123456789ab run /work/bundle/job.yaml --runs-dir /work/runs" in script
    assert "already running" in script
    assert script.index("docker rm") < script.index("docker run")


def test_status_and_snapshot_use_the_containers_own_image():
    for script in (commands.status_script(REMOTE, "j"), commands.snapshot_script(REMOTE, "j")):
        assert "docker inspect -f '{{.Config.Image}}' commander-sim-j" in script
        assert '"$img"' in script
    assert "/work/fetch/results.sqlite" in commands.snapshot_script(REMOTE, "j")


def test_stop_marks_the_job_then_sends_sigterm_with_a_grace_period():
    assert commands.stop_script(REMOTE, "j") == (
        "touch commander-sim/jobs/j/stopped && docker stop -t 60 commander-sim-j"
    )


def test_launch_clears_the_stop_marker_and_runs_the_start_script():
    assert commands.launch_script(REMOTE, "j") == (
        "rm -f commander-sim/jobs/j/stopped && sh commander-sim/jobs/j/start.sh"
    )


def run_with_fake_crontab(tmp_path: Path, script: str, existing: str) -> str:
    """Run a script with a `crontab` stand-in that keeps the table in a file; return the table.

    Like the real one, it reads all input before replacing the table.
    """
    table = tmp_path / "table"
    table.write_text(existing, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "crontab"
    fake.write_text(
        f'#!/bin/sh\nif [ "$1" = "-l" ]; then [ -s {table} ] && cat {table} || exit 1; '
        f"else cat > {table}.new && mv {table}.new {table}; fi\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)}
    subprocess.run(["sh", "-c", script], cwd=tmp_path, env=env, check=True, capture_output=True)
    return table.read_text(encoding="utf-8")


@pytest.mark.parametrize("existing", ["", "0 3 * * * backup.sh\n"])
def test_watchdog_install_adds_its_entry_and_keeps_others(tmp_path: Path, existing: str):
    table = run_with_fake_crontab(tmp_path, commands.install_watchdog_script(REMOTE), existing)
    assert "*/10 * * * *" in table and "watchdog.sh" in table
    assert existing.strip() in table
    assert (tmp_path / "commander-sim" / "watchdog.sh").is_file()
    again = run_with_fake_crontab(tmp_path, commands.install_watchdog_script(REMOTE), table)
    assert again.count("watchdog.sh") == table.count("watchdog.sh")


def test_watchdog_remove_keeps_other_entries(tmp_path: Path):
    existing = "0 3 * * * backup.sh\n*/10 * * * * cd x && sh commander-sim/watchdog.sh\n"
    table = run_with_fake_crontab(tmp_path, commands.remove_watchdog_script(REMOTE), existing)
    assert table.strip() == "0 3 * * * backup.sh"


@pytest.mark.parametrize(
    "script",
    [
        commands.start_script(REMOTE, "c" * 40, "j", 4),
        commands.status_script(REMOTE, "j"),
        commands.snapshot_script(REMOTE, "j"),
        commands.build_script(REMOTE, "c" * 40),
        commands.prepare_job_script(REMOTE, "j"),
        commands.launch_script(REMOTE, "j"),
        commands.stop_script(REMOTE, "j"),
        commands.watchdog_script(REMOTE),
        commands.install_watchdog_script(REMOTE),
        commands.remove_watchdog_script(REMOTE),
    ],
)
def test_scripts_are_valid_posix_shell(script: str):
    assert subprocess.run(["sh", "-n", "-c", script], check=False).returncode == 0
