from commander_sim.config import JobSpec, WorkerSettings
from commander_sim.runner.workers import choose_worker_count, workers_for


def test_limited_by_cores():
    assert choose_worker_count(cores=8, ram_budget_mb=64_000, heap_mb=1536) == 7


def test_limited_by_ram():
    assert choose_worker_count(cores=16, ram_budget_mb=6_000, heap_mb=1536) == 3


def test_at_least_one_worker():
    assert choose_worker_count(cores=1, ram_budget_mb=100, heap_mb=1536) == 1


def test_max_workers_caps_the_result():
    assert choose_worker_count(cores=16, ram_budget_mb=64_000, heap_mb=1536, max_workers=4) == 4


def test_workers_for_honours_job_limits():
    spec = JobSpec(
        name="t",
        decks_dir=".",
        pod=("a", "b"),
        games=1,
        workers=WorkerSettings(max=2, ram_budget_gb=64),
    )
    assert workers_for(spec) <= 2
