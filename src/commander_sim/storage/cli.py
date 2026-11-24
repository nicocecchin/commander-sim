"""`snapshot` and `progress` commands, used to watch runs on other machines."""

from pathlib import Path

import typer

from commander_sim.config import job_from_portable_json
from commander_sim.forge.output import Outcome
from commander_sim.storage.load import DatabaseError, load_databases
from commander_sim.storage.results import snapshot_database


def snapshot(database: Path, output: Path) -> None:
    """Write a consistent copy of a results database, safe to take while a run is writing."""
    if not database.is_file():
        raise typer.BadParameter(f"{database} does not exist")
    snapshot_database(database, output)
    typer.echo(f"Wrote {output}")


def progress(databases: list[Path]) -> None:
    """One line per run: games stored out of the job's total, and outcomes."""
    try:
        results = load_databases(databases)
    except DatabaseError as error:
        raise typer.BadParameter(str(error)) from None
    for run in results.runs:
        games = [g for g in results.games if g.run_id == run.run_id]
        total = job_from_portable_json(run.job_json).games
        counts = " ".join(f"{o.value}={sum(1 for g in games if g.outcome is o)}" for o in Outcome)
        typer.echo(f"{run.name}: {len(games)}/{total} games, {counts}")
