"""Command line interface."""

import threading
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn

from commander_sim.config import load_job
from commander_sim.decks.cli import all_valid, check_decks, decks_app, load_index
from commander_sim.decks.dck_format import read_dck
from commander_sim.decks.model import deck_hash
from commander_sim.forge.install import DEFAULT_VENDOR_DIR, PINNED_RELEASE, install_forge
from commander_sim.forge.invoke import SimRequest, run_sim
from commander_sim.forge.output import Outcome, SimOutput
from commander_sim.runner.executor import run_job
from commander_sim.runner.plan import balance_warnings
from commander_sim.runner.workers import workers_for
from commander_sim.stats.cli import compare, deck_table, merge, stats
from commander_sim.stats.winrates import deck_stats
from commander_sim.storage.results import ResultStore

app = typer.Typer(no_args_is_help=True, help="Headless Forge Commander simulation harness.")
forge_app = typer.Typer(no_args_is_help=True, help="Manage the local Forge installation.")
app.add_typer(forge_app, name="forge")
app.add_typer(decks_app, name="decks")
for command in (stats, compare, merge):
    app.command()(command)

DEFAULT_RUNS_DIR = Path("runs")
RESULTS_FILE = "results.sqlite"


@forge_app.command("setup")
def forge_setup(vendor_dir: Path = DEFAULT_VENDOR_DIR) -> None:
    """Download the pinned Forge release into vendor_dir (skipped if already present)."""
    typer.echo(f"Installing Forge {PINNED_RELEASE.version} into {vendor_dir} ...")
    installed = install_forge(PINNED_RELEASE, vendor_dir)
    typer.echo(f"Forge {PINNED_RELEASE.version} ready at {installed}")


def _describe(counts: dict[Outcome, int]) -> str:
    return " ".join(f"{outcome.value}={counts.get(outcome, 0)}" for outcome in Outcome)


@app.command("run")
def run(
    job_file: Path,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    vendor_dir: Path = DEFAULT_VENDOR_DIR,
    allow_invalid: bool = False,
) -> None:
    """Run a job file. Running the same job again resumes it."""
    spec = load_job(job_file)
    forge_version = PINNED_RELEASE.version
    forge_dir = vendor_dir / forge_version
    run_dir = runs_dir / spec.name
    workers = workers_for(spec)

    decks = {name: read_dck(spec.decks_dir / name) for name in spec.deck_files}
    reports = check_decks(list(decks.values()), load_index(vendor_dir))
    if not all_valid(reports) and not allow_invalid:
        typer.secho("Refusing to run invalid decks (use --allow-invalid).", fg=typer.colors.RED)
        raise typer.Exit(1)
    deck_hashes = {name: deck_hash(deck) for name, deck in decks.items()}
    ai_weak = {name: list(r.ai_weak_cards) for name, r in zip(decks, reports, strict=True)}

    for warning in balance_warnings(spec):
        typer.secho(f"Warning: {warning}", fg=typer.colors.YELLOW)
    typer.echo(f"Job '{spec.name}': {spec.games} games on {workers} workers, Forge {forge_version}")

    def simulate(request: SimRequest, home: Path, cancel: threading.Event) -> SimOutput:
        return run_sim(forge_dir, request, home, cancel)

    store = ResultStore(run_dir / RESULTS_FILE)
    try:
        run_id = store.init_run(
            spec.name, spec.model_dump_json(), forge_version, deck_hashes, ai_weak
        )
        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
        ) as progress:
            bar = progress.add_task("games", total=spec.games)

            def update(counts: dict[Outcome, int]) -> None:
                progress.update(bar, completed=sum(counts.values()), description=_describe(counts))

            update(store.outcome_counts(run_id))
            run_job(spec, store, run_id, deck_hashes, run_dir, simulate, workers, update)
        typer.echo(f"Outcomes: {_describe(store.outcome_counts(run_id))}")
        for task_index, error in store.failed_errors(run_id):
            typer.secho(f"  task {task_index} failed: {error}", fg=typer.colors.RED)
        Console().print(deck_table(deck_stats(store.read_games()), {}))
    except KeyboardInterrupt:
        typer.secho("Interrupted. Run the same command again to resume.", fg=typer.colors.YELLOW)
        raise typer.Exit(130) from None
    finally:
        store.close()
