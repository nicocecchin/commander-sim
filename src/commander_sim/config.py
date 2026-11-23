"""Job specification: everything needed to describe a run besides the deck files."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from commander_sim.forge.invoke import DEFAULT_HEAP_MB, DEFAULT_TIMEOUT_SECONDS


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ForgeSettings(_Strict):
    game_timeout_seconds: int = Field(DEFAULT_TIMEOUT_SECONDS, gt=0)
    heap_mb: int = Field(DEFAULT_HEAP_MB, ge=512)


class WorkerSettings(_Strict):
    """Limits on parallelism. `None` means derive the value from this machine."""

    max: int | None = Field(None, gt=0)
    ram_budget_gb: float | None = Field(None, gt=0)


class JobSpec(_Strict):
    name: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    decks_dir: Path
    pod: tuple[str, ...] = Field(min_length=2)
    games: int = Field(gt=0)
    games_per_task: int = Field(4, gt=0)
    seed: int = 0
    forge: ForgeSettings = ForgeSettings()
    workers: WorkerSettings = WorkerSettings()

    @field_validator("pod")
    @classmethod
    def _pod_decks_are_distinct(cls, pod: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(pod)) != len(pod):
            raise ValueError("pod must not list the same deck twice")
        return pod


def load_job(path: Path) -> JobSpec:
    """Load a job file. A relative `decks_dir` is resolved against the job file's folder."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec = JobSpec.model_validate(raw)
    return spec.model_copy(update={"decks_dir": (path.parent / spec.decks_dir).resolve()})
