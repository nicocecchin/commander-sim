"""Job specification: everything needed to describe a run besides the deck files."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from commander_sim.forge.invoke import DEFAULT_HEAP_MB, DEFAULT_TIMEOUT_SECONDS

POD_SIZE = 4


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ForgeSettings(_Strict):
    game_timeout_seconds: int = Field(DEFAULT_TIMEOUT_SECONDS, gt=0)
    heap_mb: int = Field(DEFAULT_HEAP_MB, ge=512)


class WorkerSettings(_Strict):
    """Limits on parallelism. `None` means derive the value from this machine."""

    max: int | None = Field(None, gt=0)
    ram_budget_gb: float | None = Field(None, gt=0)


def _require_distinct(decks: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(decks)) != len(decks):
        raise ValueError("a deck must not be listed twice")
    return decks


class PodMatchup(_Strict):
    """The same decks play each other in every game."""

    kind: Literal["pod"]
    decks: tuple[str, ...] = Field(min_length=2, max_length=6)

    distinct_decks = field_validator("decks")(_require_distinct)


class ABMatchup(_Strict):
    """Two variants of a deck, each facing the same opponents drawn from `field`."""

    kind: Literal["ab"]
    variants: tuple[str, str]
    field: tuple[str, ...] = Field(min_length=POD_SIZE - 1)

    distinct_decks = field_validator("field")(_require_distinct)

    @model_validator(mode="after")
    def _variants_are_not_in_the_field(self) -> "ABMatchup":
        _require_distinct((*self.variants, *self.field))
        return self


class LeagueMatchup(_Strict):
    """Every combination of `POD_SIZE` decks from `decks` plays, to rate all decks together."""

    kind: Literal["league"]
    decks: tuple[str, ...] = Field(min_length=POD_SIZE)

    distinct_decks = field_validator("decks")(_require_distinct)


Matchup = Annotated[PodMatchup | ABMatchup | LeagueMatchup, Field(discriminator="kind")]


class JobSpec(_Strict):
    """`games` is the total; for an A/B job it is split equally between the two variants."""

    name: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    decks_dir: Path
    matchup: Matchup
    games: int = Field(gt=0)
    games_per_task: int = Field(4, gt=0)
    seed: int = 0
    forge: ForgeSettings = ForgeSettings()
    workers: WorkerSettings = WorkerSettings()

    @model_validator(mode="after")
    def _ab_games_split_evenly(self) -> "JobSpec":
        if isinstance(self.matchup, ABMatchup) and self.games % 2:
            raise ValueError("an A/B job needs an even number of games (split between variants)")
        return self

    @property
    def deck_files(self) -> tuple[str, ...]:
        """Every deck file the job uses."""
        match self.matchup:
            case ABMatchup(variants=variants, field=field):
                return (*variants, *field)
            case PodMatchup(decks=decks) | LeagueMatchup(decks=decks):
                return decks


def load_job(path: Path) -> JobSpec:
    """Load a job file. A relative `decks_dir` is resolved against the job file's folder."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec = JobSpec.model_validate(raw)
    return spec.model_copy(update={"decks_dir": (path.parent / spec.decks_dir).resolve()})
