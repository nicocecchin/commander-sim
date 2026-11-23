"""Read and write Forge `.dck` deck files."""

import re
from pathlib import Path

from commander_sim.decks.model import Deck, DeckCard

_CARD_LINE = re.compile(r"^(?P<count>\d+)\s+(?P<name>[^|]+)")
_SECTION_FOR = {"commander": "commanders", "main": "main"}


def write_dck(deck: Deck, path: Path) -> None:
    """Write `deck` for Forge. Set codes are omitted so Forge picks any printing."""
    lines = ["[metadata]", f"Name={deck.name}", "[Commander]"]
    lines += [f"{card.count} {card.name}" for card in deck.commanders]
    lines += ["[Main]"]
    lines += [f"{card.count} {card.name}" for card in deck.main]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_dck(path: Path) -> Deck:
    name = path.stem
    sections: dict[str, list[DeckCard]] = {"commanders": [], "main": []}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("["):
            current = _SECTION_FOR.get(line.strip("[]").lower())
        elif line.lower().startswith("name=") and current is None:
            name = line.split("=", 1)[1].strip()
        elif current and (match := _CARD_LINE.match(line)):
            sections[current].append(DeckCard(match["name"].strip(), int(match["count"])))
    return Deck(name=name, commanders=tuple(sections["commanders"]), main=tuple(sections["main"]))
