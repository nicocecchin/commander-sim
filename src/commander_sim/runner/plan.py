"""Split a job into tasks: one Forge launch each, with a fixed seat order and seed.

Seat balance: a task is always one rotation of a base seating, and every rotation of a base
seating is played before the next base seating starts, so each deck sits in each seat equally
often. An A/B scenario seats variant A and variant B identically (same opponents, same seats,
same seed).
"""

import itertools
import math
import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from commander_sim.config import POD_SIZE, ABMatchup, JobSpec, LeagueMatchup, PodMatchup

_SEED_SPACE = 2**31 - 1
_PLACEHOLDER = ""

Seating = tuple[str, ...]
Scenario = tuple[Seating, ...]  # seatings that share a seed; two for an A/B scenario


@dataclass(frozen=True)
class Task:
    index: int
    seats: Seating
    games: int
    seed: int


def derive_seed(job_seed: int, scenario_index: int) -> int:
    """Deterministic per-scenario seed, so a task can be replayed exactly."""
    return random.Random(f"{job_seed}:{scenario_index}").randrange(_SEED_SPACE)


def _rotations(base: Sequence[str]) -> Iterator[Seating]:
    for shift in range(len(base)):
        yield tuple(base[shift:]) + tuple(base[:shift])


def _pod_scenarios(decks: tuple[str, ...], rng: random.Random) -> Iterator[Scenario]:
    while True:
        for seating in _rotations(rng.sample(decks, len(decks))):
            yield (seating,)


def _league_scenarios(decks: tuple[str, ...], rng: random.Random) -> Iterator[Scenario]:
    pods = list(itertools.combinations(decks, POD_SIZE))
    while True:
        rng.shuffle(pods)
        for pod in pods:
            for seating in _rotations(rng.sample(pod, POD_SIZE)):
                yield (seating,)


def _ab_scenarios(
    variants: tuple[str, str], field: tuple[str, ...], rng: random.Random
) -> Iterator[Scenario]:
    opponent_sets = list(itertools.combinations(field, POD_SIZE - 1))
    while True:
        rng.shuffle(opponent_sets)
        for opponents in opponent_sets:
            base = rng.sample([_PLACEHOLDER, *opponents], POD_SIZE)
            for seating in _rotations(base):
                yield tuple(
                    tuple(variant if deck == _PLACEHOLDER else deck for deck in seating)
                    for variant in variants
                )


def _scenarios(spec: JobSpec) -> Iterator[Scenario]:
    rng = random.Random(spec.seed)
    match spec.matchup:
        case PodMatchup(decks=decks):
            return _pod_scenarios(decks, rng)
        case LeagueMatchup(decks=decks):
            return _league_scenarios(decks, rng)
        case ABMatchup(variants=variants, field=field):
            return _ab_scenarios(variants, field, rng)


def plan_tasks(spec: JobSpec) -> list[Task]:
    """All tasks of a job. Deterministic, so a resumed run sees the same plan."""
    games_per_scenario_seating = spec.games_per_task
    remaining = spec.games // (2 if isinstance(spec.matchup, ABMatchup) else 1)
    tasks: list[Task] = []
    for scenario_index, scenario in enumerate(_scenarios(spec)):
        if remaining <= 0:
            break
        games = min(games_per_scenario_seating, remaining)
        seed = derive_seed(spec.seed, scenario_index)
        tasks += [Task(len(tasks) + i, seats, games, seed) for i, seats in enumerate(scenario)]
        remaining -= games
    return tasks


def balance_warnings(spec: JobSpec) -> list[str]:
    """Explain how this game count falls short of perfectly even seats and opponents."""
    per_seating = spec.games_per_task
    warnings = []
    match spec.matchup:
        case PodMatchup(decks=decks):
            seat_cycle = len(decks) * per_seating
            games, seat_unit = spec.games, "games"
            opponent_cycle = None
        case LeagueMatchup(decks=decks):
            seat_cycle = POD_SIZE * per_seating
            games, seat_unit = spec.games, "games"
            opponent_cycle = math.comb(len(decks), POD_SIZE) * seat_cycle
        case ABMatchup(field=field):
            seat_cycle = POD_SIZE * per_seating
            games, seat_unit = spec.games // 2, "games per variant"
            opponent_cycle = math.comb(len(field), POD_SIZE - 1) * seat_cycle
    if games % seat_cycle:
        warnings.append(
            f"{games} {seat_unit} is not a multiple of {seat_cycle}: "
            "decks will not sit in every seat equally often."
        )
    if opponent_cycle and games % opponent_cycle:
        warnings.append(
            f"{games} {seat_unit} is not a multiple of {opponent_cycle}: "
            "not every opponent combination is played equally often."
        )
    return warnings
