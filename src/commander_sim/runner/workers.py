"""Decide how many Forge JVMs to run at once."""

import os

import psutil

from commander_sim.config import JobSpec

DEFAULT_RAM_FRACTION = 0.8


def choose_worker_count(
    cores: int, ram_budget_mb: float, heap_mb: int, max_workers: int | None = None
) -> int:
    """`min(cores - 1, ram_budget / heap_per_worker)`, at least 1, capped by `max_workers`."""
    count = max(1, min(cores - 1, int(ram_budget_mb // heap_mb)))
    return min(count, max_workers) if max_workers else count


def default_ram_budget_mb() -> float:
    """A fraction of the memory currently available on this machine."""
    return psutil.virtual_memory().available / 2**20 * DEFAULT_RAM_FRACTION


def cpu_cores() -> int:
    return os.cpu_count() or 1


def workers_for(spec: JobSpec) -> int:
    """Worker count for a job, honouring its limits and defaulting to this machine's capacity."""
    budget_gb = spec.workers.ram_budget_gb
    budget_mb = budget_gb * 1024 if budget_gb else default_ram_budget_mb()
    return choose_worker_count(cpu_cores(), budget_mb, spec.forge.heap_mb, spec.workers.max)
