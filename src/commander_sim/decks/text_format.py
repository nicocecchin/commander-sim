"""Parse plain-text, Moxfield-text and Archidekt-text decklists into a `Deck`."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from commander_sim.decks.model import Deck, DeckCard

_LINE = re.compile(r"^\s*(?P<count>\d+)\s*x?\s+(?P<rest>.+?)\s*$", re.IGNORECASE)
_CATEGORIES = re.compile(r"\s*\[(?P<cats>[^\]]*)\]\s*$")
_TAGS = re.compile(r"\s*(\^[^^]*\^|\*[A-Z]\*)")
_PRINTING = re.compile(r"\s+\((?P<set>[A-Za-z0-9]+)\)(?:\s+\S+)?\s*$")
_HEADER = re.compile(r"^\s*(?P<word>[A-Za-z ]+?)\s*(?:\(\d+\))?\s*:?\s*$")

_COMMANDER_HEADERS = {"commander", "commanders", "command zone"}
_MAIN_HEADERS = {"deck", "main", "mainboard", "main deck"}
_IGNORED_HEADERS = {"sideboard", "maybeboard", "considering", "companion", "tokens"}
_MAX_TRAILING_COMMANDERS = 2


class DeckParseError(ValueError):
    """A line of the decklist could not be understood."""


@dataclass
class _Sections:
    commanders: list[DeckCard] = field(default_factory=list)
    main_blocks: list[list[DeckCard]] = field(default_factory=lambda: [[]])


def _parse_card(line: str) -> tuple[DeckCard, bool] | None:
    """Return the card on this line and whether its Archidekt category marks it a commander."""
    match = _LINE.match(line)
    if not match:
        return None
    rest = _TAGS.sub("", match["rest"])
    is_commander = False
    if categories := _CATEGORIES.search(rest):
        is_commander = "commander" in categories["cats"].lower()
        rest = rest[: categories.start()]
    rest = _PRINTING.sub("", rest)
    return DeckCard(name=rest.strip(), count=int(match["count"])), is_commander


def _section_for_header(line: str) -> str:
    header = _HEADER.match(line)
    word = header["word"].lower() if header else ""
    if word in _COMMANDER_HEADERS:
        return "commander"
    if word in _MAIN_HEADERS:
        return "main"
    if word in _IGNORED_HEADERS:
        return "ignored"
    raise DeckParseError(f"Unrecognised line: {line.strip()!r} (expected '<count> <card name>')")


def parse_deck_text(text: str, name: str, can_be_commander: Callable[[str], bool]) -> Deck:
    """Parse a decklist.

    Commanders come from a "Commander" header or an Archidekt `[Commander]` category. Failing
    that, a final blank-line-separated block of one or two commander-eligible cards is taken as
    the commanders. Otherwise the deck is returned without commanders; validation reports it.
    """
    sections = _Sections()
    section = "main"
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if section == "main" and sections.main_blocks[-1]:
                sections.main_blocks.append([])
        elif stripped.startswith(("//", "#")):
            continue
        elif parsed := _parse_card(line):
            card, marked_commander = parsed
            if marked_commander or section == "commander":
                sections.commanders.append(card)
            elif section == "main":
                sections.main_blocks[-1].append(card)
        else:
            section = _section_for_header(line)
    blocks = [block for block in sections.main_blocks if block]
    commanders = sections.commanders
    if not commanders and len(blocks) > 1:
        last = blocks[-1]
        if len(last) <= _MAX_TRAILING_COMMANDERS and all(can_be_commander(c.name) for c in last):
            commanders = last
            blocks = blocks[:-1]
    main = [card for block in blocks for card in block]
    return Deck(name=name, commanders=tuple(commanders), main=tuple(main))
