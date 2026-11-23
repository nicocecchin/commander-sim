"""Deck data shared by every importer, validator and writer."""

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
