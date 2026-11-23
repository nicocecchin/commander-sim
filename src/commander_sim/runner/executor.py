"""Run a job's tasks on a pool of workers, with retries, resume and crash recording."""

import itertools
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from commander_sim.config import JobSpec
from commander_sim.forge.invoke import SimError, SimRequest
from commander_sim.forge.output import GameResult, Outcome, SimOutput
from commander_sim.runner.plan import Task, plan_tasks
from commander_sim.storage.results import ResultStore, TaskRecord

MAX_ATTEMPTS = 3

Simulate = Callable[[SimRequest, Path, threading.Event], SimOutput]
ProgressCallback = Callable[[dict[Outcome, int]], None]


def _request_for(spec: JobSpec, task: Task) -> SimRequest:
    return SimRequest(
        deck_dir=spec.decks_dir,
        decks=task.seats,
        games=task.games,
        seed=task.seed,
        game_timeout_seconds=spec.forge.game_timeout_seconds,
        heap_mb=spec.forge.heap_mb,
    )


def _play_task(
    spec: JobSpec, task: Task, home: Path, simulate: Simulate, cancel: threading.Event
) -> TaskRecord:
    """Run one task, retrying a failed launch. After the last failure, record crashes."""
    error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            output = simulate(_request_for(spec, task), home, cancel)
        except SimError as exc:
            error = str(exc)
            continue
        return TaskRecord(task.index, task.seed, task.seats, output.games, attempt)
    crashes = tuple(
        GameResult(number, Outcome.CRASH, None, None, None) for number in range(1, task.games + 1)
    )
    return TaskRecord(task.index, task.seed, task.seats, crashes, MAX_ATTEMPTS, error)


def run_job(
    spec: JobSpec,
    store: ResultStore,
    run_id: str,
    forge_version: str,
    run_dir: Path,
    simulate: Simulate,
    workers: int,
    on_progress: ProgressCallback | None = None,
) -> None:
    """Play every task not yet finished, saving each one as it completes.

    Each worker thread keeps its own `user.home` under `run_dir/workers/<n>/home`. On
    KeyboardInterrupt the running Forge processes are killed, finished tasks stay saved, and the
    exception is re-raised; running the same job again resumes.
    """
    done = store.completed_tasks()
    pending = [task for task in plan_tasks(spec) if task.index not in done]
    cancel = threading.Event()
    slots = itertools.count()
    local = threading.local()

    def assign_slot() -> None:
        local.home = run_dir / "workers" / str(next(slots)) / "home"

    def work(task: Task) -> TaskRecord:
        return _play_task(spec, task, local.home, simulate, cancel)

    executor = ThreadPoolExecutor(max_workers=workers, initializer=assign_slot)
    try:
        futures = [executor.submit(work, task) for task in pending]
        for future in as_completed(futures):
            store.save_task(future.result(), run_id, forge_version)
            if on_progress:
                on_progress(store.outcome_counts())
    except BaseException:
        cancel.set()
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
