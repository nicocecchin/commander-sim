"""`stats`, `compare` and `merge` commands."""

from collections import defaultdict
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from commander_sim.decks.playgroup import DEFAULT_PLAYGROUP_FILE, load_owners
from commander_sim.stats.compare import compare_decks
from commander_sim.stats.ratings import fit_ratings
from commander_sim.stats.winrates import DeckStats, deck_stats, deck_versions, seat_stats
from commander_sim.storage.results import GameRecord, ResultStore, RunInfo, RunMismatchError

DISCLAIMER = (
    "Results measure each deck as piloted by the Forge AI, which is heuristic: it plays aggro and "
    "midrange best and most combo decks badly."
)

console = Console()


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _interval(interval: tuple[float, float]) -> str:
    return f"{_percent(interval[0])} - {_percent(interval[1])}"


def _win_length(stats: DeckStats) -> str:
    if stats.mean_win_turn is None or stats.mean_win_rounds is None:
        return "-"
    return f"{stats.mean_win_turn:.1f} / {stats.mean_win_rounds:.1f}"


def _label(deck: str, owners: dict[str, str]) -> str:
    name = deck.removesuffix(".dck")
    return f"{name} ({owners[deck]})" if deck in owners else name


def load_results(paths: list[Path]) -> tuple[list[RunInfo], list[GameRecord]]:
    """Read every run and game from the given databases; the same run twice is an error."""
    runs: list[RunInfo] = []
    games: list[GameRecord] = []
    for path in paths:
        if not path.is_file():
            raise typer.BadParameter(f"{path} does not exist")
        store = ResultStore(path)
        try:
            runs += store.read_runs()
            games += store.read_games()
        finally:
            store.close()
    ids = [run.run_id for run in runs]
    if len(ids) != len(set(ids)):
        raise typer.BadParameter("The same run appears in more than one database")
    return runs, games


def deck_table(stats: list[DeckStats], owners: dict[str, str]) -> Table:
    table = Table(
        "Deck",
        "Games",
        "Wins",
        "Winrate (95% CI)",
        "Win length: turns / rounds",
        "Timeouts",
        "Crashes",
    )
    for s in stats:
        table.add_row(
            _label(s.deck, owners),
            str(s.decided),
            str(s.wins),
            f"{_percent(s.winrate)}  [{_interval(s.interval)}]",
            _win_length(s),
            f"{s.timeouts} ({_percent(s.timeout_rate)})",
            str(s.crashes),
        )
    return table


def ai_weakness_notes(runs: list[RunInfo], owners: dict[str, str]) -> list[str]:
    weak: dict[str, set[str]] = defaultdict(set)
    for run in runs:
        for deck, cards in run.ai_weak_cards.items():
            weak[deck].update(cards)
    return [
        f"{_label(deck, owners)}: {', '.join(sorted(cards))}"
        for deck, cards in sorted(weak.items())
        if cards
    ]


def print_footer(runs: list[RunInfo], games: list[GameRecord], owners: dict[str, str]) -> None:
    for deck, hashes in deck_versions(games).items():
        console.print(
            f"[yellow]Warning:[/] '{deck}' appears with {len(hashes)} different card lists; "
            "its results mix versions."
        )
    if notes := ai_weakness_notes(runs, owners):
        console.print("\nCards Forge says its AI plays badly:")
        for note in notes:
            console.print(f"  {note}")
    console.print(
        "\nWin length: a turn is one player's turn, a round is one pass around the table "
        "(eliminated players skip theirs)."
    )
    console.print(f"\n{DISCLAIMER}")


def stats(
    databases: list[Path],
    playgroup: Path = DEFAULT_PLAYGROUP_FILE,
    bootstrap: int = typer.Option(200, help="Bootstrap resamples for rating intervals."),
) -> None:
    """Winrates (with 95% intervals), seat winrates and ratings for one or more run databases."""
    runs, games = load_results(databases)
    owners = load_owners(playgroup)
    if not games:
        raise typer.BadParameter("No games stored yet")
    console.print(deck_table(deck_stats(games), owners))

    seat_table = Table("Seat", "Games", "Winrate (95% CI)")
    for s in seat_stats(games):
        seat_table.add_row(
            str(s.seat), str(s.decided), f"{_percent(s.winrate)}  [{_interval(s.interval)}]"
        )
    console.print(seat_table)

    ratings_table = Table("Deck", "Strength", "Expected winrate vs 3 reference decks (95% CI)")
    for r in fit_ratings(games, bootstrap=bootstrap):
        ratings_table.add_row(
            _label(r.deck, owners),
            f"{r.strength:.2f}",
            f"{_percent(r.expected_winrate)}  [{_interval(r.interval)}]",
        )
    console.print(ratings_table)
    print_footer(runs, games, owners)


def compare(
    databases: list[Path],
    a: str = typer.Option(..., help="Deck file name of variant A, e.g. my-deck-a.dck"),
    b: str = typer.Option(..., help="Deck file name of variant B."),
    playgroup: Path = DEFAULT_PLAYGROUP_FILE,
) -> None:
    """Compare two decks' winrates, with a warning if the sample or the fields do not allow it."""
    runs, games = load_results(databases)
    try:
        result = compare_decks(games, a, b)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    owners = load_owners(playgroup)
    console.print(deck_table([result.a, result.b], owners))
    low, high = result.interval
    console.print(
        f"\n{b} minus {a}: {result.difference * 100:+.1f} points "
        f"(95% CI {low * 100:+.1f} to {high * 100:+.1f}), p = {result.p_value:.3f}"
    )
    console.print(
        f"With this many games, differences below {result.min_detectable * 100:.1f} points "
        "cannot reliably be detected."
    )
    for warning in result.warnings:
        console.print(f"[yellow]Warning:[/] {warning}")
    print_footer(runs, games, owners)


def merge(output: Path, databases: list[Path]) -> None:
    """Combine run databases into a new one for analysis. Refuses runs it already holds."""
    if output.exists():
        raise typer.BadParameter(f"{output} already exists")
    target = ResultStore(output)
    failure: RunMismatchError | None = None
    try:
        for path in databases:
            source = ResultStore(path)
            try:
                typer.echo(f"{path}: {len(target.import_runs(source))} run(s)")
            finally:
                source.close()
    except RunMismatchError as error:
        failure = error
    finally:
        target.close()
    if failure:
        output.unlink()
        raise typer.BadParameter(str(failure))
    typer.echo(f"Wrote {output}")
