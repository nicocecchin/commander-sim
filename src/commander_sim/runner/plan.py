"""Split a job into tasks: one Forge launch each, with a fixed seat order and seed."""

import itertools
import random
from dataclasses import dataclass

from commander_sim.config import JobSpec

_SEED_SPACE = 2**31 - 1


@dataclass(frozen=True)
class Task:
    index: int
    seats: tuple[str, ...]
    games: int
    seed: int


def derive_seed(job_seed: int, task_index: int) -> int:
    """Deterministic per-task seed, so a task can be replayed exactly."""
    return random.Random(f"{job_seed}:{task_index}").randrange(_SEED_SPACE)


def seat_orders(pod: tuple[str, ...], job_seed: int) -> list[tuple[str, ...]]:
    """Every ordering of the pod, in a seeded shuffle so a partial run stays near balanced."""
    orders = list(itertools.permutations(pod))
    random.Random(job_seed).shuffle(orders)
    return orders


def plan_tasks(spec: JobSpec) -> list[Task]:
    orders = seat_orders(spec.pod, spec.seed)
    tasks = []
    for index, first_game in enumerate(range(0, spec.games, spec.games_per_task)):
        tasks.append(
            Task(
                index=index,
                seats=orders[index % len(orders)],
                games=min(spec.games_per_task, spec.games - first_game),
                seed=derive_seed(spec.seed, index),
            )
        )
    return tasks


def balance_warning(spec: JobSpec) -> str | None:
    """Return a warning if the game count cannot rotate every seat order equally often."""
    cycle = len(seat_orders(spec.pod, spec.seed)) * spec.games_per_task
    if spec.games % cycle == 0:
        return None
    return (
        f"{spec.games} games is not a multiple of {cycle} "
        f"({len(spec.pod)}-deck pod x {spec.games_per_task} games per launch): "
        "seats will not be perfectly balanced."
    )
