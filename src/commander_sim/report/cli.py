"""`report` command."""

from pathlib import Path

import typer

from commander_sim.decks.playgroup import DEFAULT_PLAYGROUP_FILE, load_owners
from commander_sim.report.render import write_report
from commander_sim.storage.load import DatabaseError, load_databases

DEFAULT_REPORT_FILE = Path("report.html")


def report(
    databases: list[Path],
    out: Path = DEFAULT_REPORT_FILE,
    playgroup: Path = DEFAULT_PLAYGROUP_FILE,
    bootstrap: int = typer.Option(200, help="Bootstrap resamples for rating intervals."),
) -> None:
    """Write a self-contained HTML report for one or more run databases."""
    try:
        results = load_databases(databases)
    except DatabaseError as error:
        raise typer.BadParameter(str(error)) from None
    if not results.games:
        raise typer.BadParameter("No games stored yet")
    write_report(results, load_owners(playgroup), out, bootstrap)
    typer.echo(f"Wrote {out}")
