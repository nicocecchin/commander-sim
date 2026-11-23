"""Check a deck against Commander rules and against what Forge can play."""

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from commander_sim.decks.dck_format import read_dck
from commander_sim.decks.model import COMMANDER_DECK_SIZE, Deck, DeckCard
from commander_sim.forge.cards import AI_WEAK_FLAG, CardIndex, CardInfo

_MAX_COMMANDERS = 2


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    severity: Severity
    message: str


@dataclass(frozen=True)
class ValidationReport:
    deck_name: str
    issues: tuple[Issue, ...]
    ai_weak_cards: tuple[str, ...] = ()

    @property
    def errors(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.WARNING)

    @property
    def ok(self) -> bool:
        return not self.errors


def _unknown_card_issues(cards: tuple[DeckCard, ...], index: CardIndex) -> list[Issue]:
    issues = []
    for card in cards:
        if index.lookup(card.name) is None:
            hint = index.suggest(card.name)
            suffix = f" (did you mean: {', '.join(hint)}?)" if hint else ""
            issues.append(Issue(Severity.ERROR, f"Unknown card '{card.name}'{suffix}"))
    return issues


def _commander_issues(commanders: list[CardInfo]) -> list[Issue]:
    if not commanders:
        return [Issue(Severity.ERROR, "No commander found")]
    if len(commanders) > _MAX_COMMANDERS:
        return [Issue(Severity.ERROR, f"{len(commanders)} commanders (at most 2 allowed)")]
    issues = [
        Issue(Severity.ERROR, f"'{c.name}' cannot be a commander")
        for c in commanders
        if not (c.can_be_commander or c.is_background)
    ]
    if len(commanders) == _MAX_COMMANDERS and not all(
        c.has_pairing_keyword or c.is_background for c in commanders
    ):
        names = " and ".join(c.name for c in commanders)
        issues.append(Issue(Severity.ERROR, f"{names} cannot be paired (no partner ability)"))
    return issues


def _duplicate_issues(cards: list[tuple[DeckCard, CardInfo]]) -> list[Issue]:
    counts: Counter[str] = Counter()
    for card, info in cards:
        if not (info.is_basic_land or info.allows_any_number):
            counts[info.name] += card.count
    return [
        Issue(Severity.ERROR, f"{count} copies of '{name}' (singleton format)")
        for name, count in counts.items()
        if count > 1
    ]


def _identity_issues(
    commanders: list[CardInfo], cards: list[tuple[DeckCard, CardInfo]]
) -> list[Issue]:
    allowed = frozenset().union(*(c.color_identity for c in commanders))
    return [
        Issue(
            Severity.WARNING,
            f"'{info.name}' has colours outside the commander's identity "
            f"({''.join(sorted(info.color_identity - allowed))})",
        )
        for _, info in cards
        if not info.color_identity <= allowed
    ]


def _ai_weak_cards(cards: list[tuple[DeckCard, CardInfo]]) -> tuple[str, ...]:
    return tuple(sorted({info.name for _, info in cards if AI_WEAK_FLAG in info.ai_flags}))


def validate_deck(deck: Deck, index: CardIndex) -> ValidationReport:
    issues = _unknown_card_issues((*deck.commanders, *deck.main), index)

    def known(cards: tuple[DeckCard, ...]) -> list[tuple[DeckCard, CardInfo]]:
        return [(c, info) for c in cards if (info := index.lookup(c.name))]

    commanders = known(deck.commanders)
    main = known(deck.main)
    commander_infos = [info for _, info in commanders]
    issues += _commander_issues(commander_infos)
    if deck.size != COMMANDER_DECK_SIZE:
        issues.append(
            Issue(Severity.ERROR, f"Deck has {deck.size} cards, expected {COMMANDER_DECK_SIZE}")
        )
    issues += _duplicate_issues(commanders + main)
    if commander_infos:
        issues += _identity_issues(commander_infos, main)
    weak = _ai_weak_cards(commanders + main)
    if weak:
        issues.append(
            Issue(
                Severity.WARNING,
                f"Forge marks {len(weak)} card(s) as played badly by its AI: {', '.join(weak)}",
            )
        )
    return ValidationReport(deck.name, tuple(issues), weak)


def validate_dck_files(
    deck_dir: Path, file_names: tuple[str, ...], index: CardIndex
) -> list[ValidationReport]:
    return [validate_deck(read_dck(deck_dir / name), index) for name in file_names]
