"""Deck data shared by every importer, validator and writer."""

import hashlib
from dataclasses import dataclass

COMMANDER_DECK_SIZE = 100


@dataclass(frozen=True)
class DeckCard:
    name: str
    count: int = 1


@dataclass(frozen=True)
class Deck:
    name: str
    commanders: tuple[DeckCard, ...]
    main: tuple[DeckCard, ...]

    @property
    def size(self) -> int:
        return sum(card.count for card in (*self.commanders, *self.main))


def deck_hash(deck: Deck) -> str:
    """Short fingerprint of a deck's card list (names, counts and commanders; not its name)."""
    lines = sorted(
        [f"C {c.count} {c.name.lower()}" for c in deck.commanders]
        + [f"M {c.count} {c.name.lower()}" for c in deck.main]
    )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:12]
