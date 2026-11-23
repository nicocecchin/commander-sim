"""`commander-sim decks ...` commands and the pre-run validation gate."""

import re
import shutil
from pathlib import Path

import typer

from commander_sim.decks.dck_format import read_dck, write_dck
from commander_sim.decks.model import Deck, DeckCard
from commander_sim.decks.text_format import DeckParseError, parse_deck_text
from commander_sim.decks.validate import Severity, ValidationReport, validate_deck
from commander_sim.forge.cards import CardIndex, load_card_index
from commander_sim.forge.install import DEFAULT_VENDOR_DIR, PINNED_RELEASE

DEFAULT_DECKS_DIR = Path("decks") / "imported"
PRECON_DIR = Path("res") / "quest" / "commanderprecons"

decks_app = typer.Typer(no_args_is_help=True, help="Import and validate decklists.")


def load_index(vendor_dir: Path) -> CardIndex:
    typer.echo("Loading Forge card database ...")
    return load_card_index(vendor_dir / PINNED_RELEASE.version)


def print_report(report: ValidationReport) -> None:
    status = "OK" if report.ok else "INVALID"
    typer.secho(f"{report.deck_name}: {status}", bold=True)
    for issue in report.issues:
        color = typer.colors.RED if issue.severity is Severity.ERROR else typer.colors.YELLOW
        typer.secho(f"  {issue.severity.value}: {issue.message}", fg=color)


def check_decks(decks: list[Deck], index: CardIndex) -> bool:
    """Print a report per deck; return True when none has errors."""
    reports = [validate_deck(deck, index) for deck in decks]
    for report in reports:
        print_report(report)
    return all(report.ok for report in reports)


def _clean_name(forge_name: str) -> str:
    return re.sub(r"\s*\[[^\]]*\]", "", forge_name).strip()


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _decks_in(path: Path, index: CardIndex) -> list[Deck]:
    if path.is_dir():
        return [read_dck(p) for p in sorted(path.glob("*.dck"))]
    if path.suffix.lower() == ".dck":
        return [read_dck(path)]
    return [_parse_text_file(path, path.stem, index)]


def _parse_text_file(path: Path, name: str, index: CardIndex) -> Deck:
    def can_be_commander(card_name: str) -> bool:
        info = index.lookup(card_name)
        return bool(info and (info.can_be_commander or info.is_background))

    try:
        return parse_deck_text(path.read_text(encoding="utf-8"), name, can_be_commander)
    except DeckParseError as error:
        typer.secho(f"{path}: {error}", fg=typer.colors.RED)
        raise typer.Exit(1) from None


def _canonical(deck: Deck, index: CardIndex) -> Deck:
    """Rewrite card names to the names Forge uses (e.g. split cards as 'A // B')."""

    def fix(cards: tuple[DeckCard, ...]) -> tuple[DeckCard, ...]:
        return tuple(
            DeckCard(info.name if (info := index.lookup(card.name)) else card.name, card.count)
            for card in cards
        )

    return Deck(deck.name, fix(deck.commanders), fix(deck.main))


@decks_app.command("validate")
def validate(paths: list[Path], vendor_dir: Path = DEFAULT_VENDOR_DIR) -> None:
    """Validate .dck files, folders of them, or text decklists."""
    index = load_index(vendor_dir)
    decks = [deck for path in paths for deck in _decks_in(path, index)]
    if not check_decks(decks, index):
        raise typer.Exit(1)


@decks_app.command("import")
def import_deck(
    source: Path,
    name: str = typer.Option(..., help="Deck name; also the output file name."),
    out_dir: Path = DEFAULT_DECKS_DIR,
    vendor_dir: Path = DEFAULT_VENDOR_DIR,
    allow_invalid: bool = False,
) -> None:
    """Convert a Moxfield / Archidekt / plain-text export to a Forge .dck file."""
    index = load_index(vendor_dir)
    deck = _canonical(_parse_text_file(source, name, index), index)
    if not check_decks([deck], index) and not allow_invalid:
        typer.secho("Not written (use --allow-invalid to write anyway).", fg=typer.colors.RED)
        raise typer.Exit(1)
    target = out_dir / f"{_slug(name)}.dck"
    write_dck(deck, target)
    shutil.copyfile(source, target.with_suffix(".source.txt"))
    typer.echo(f"Wrote {target}")


@decks_app.command("import-precon")
def import_precons(
    queries: list[str],
    out_dir: Path = DEFAULT_DECKS_DIR,
    vendor_dir: Path = DEFAULT_VENDOR_DIR,
) -> None:
    """Copy precon decklists that ship with Forge, e.g. 'Temur Roar' 'Counter Blitz'."""
    precon_dir = vendor_dir / PINNED_RELEASE.version / PRECON_DIR
    index = load_index(vendor_dir)
    decks = []
    for query in queries:
        matches = [p for p in sorted(precon_dir.glob("*.dck")) if query.lower() in p.stem.lower()]
        if len(matches) != 1:
            found = ", ".join(_clean_name(p.stem) for p in matches) or "none"
            typer.secho(f"'{query}' must match one precon (matches: {found})", fg=typer.colors.RED)
            raise typer.Exit(1)
        original = read_dck(matches[0])
        name = _clean_name(original.name)
        decks.append(_canonical(Deck(name, original.commanders, original.main), index))
    check_decks(decks, index)
    for deck in decks:
        target = out_dir / f"{_slug(deck.name)}.dck"
        write_dck(deck, target)
        typer.echo(f"Wrote {target}")
