"""The code version to run remotely: the git commit checked out here."""

import subprocess
from pathlib import Path


class SourceError(RuntimeError):
    """The working copy cannot be shipped as a commit."""


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise SourceError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def clean_head_commit(repo: Path) -> str:
    """The HEAD commit, refusing when tracked files have uncommitted changes (they would be
    silently left out of what runs remotely)."""
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise SourceError("Commit your changes first: the remote runs the committed code only")
    return _git(repo, "rev-parse", "HEAD")


def write_source_archive(repo: Path, commit: str, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "archive", "--format=tar", "-o", str(out), commit)
    return out
