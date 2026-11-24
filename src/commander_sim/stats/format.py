"""Text formatting shared by the CLI tables and the HTML report."""

from collections import defaultdict

from commander_sim.storage.results import RunInfo

DISCLAIMER = (
    "Results measure each deck as piloted by the Forge AI, which is heuristic: it plays aggro and "
    "midrange best and most combo decks badly."
)


def percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def interval_text(interval: tuple[float, float]) -> str:
    return f"{percent(interval[0])} - {percent(interval[1])}"


def deck_label(deck: str, owners: dict[str, str]) -> str:
    name = deck.removesuffix(".dck")
    return f"{name} ({owners[deck]})" if deck in owners else name


def ai_weakness_notes(runs: list[RunInfo], owners: dict[str, str]) -> list[str]:
    """One line per deck listing the cards Forge says its AI plays badly."""
    weak: dict[str, set[str]] = defaultdict(set)
    for run in runs:
        for deck, cards in run.ai_weak_cards.items():
            weak[deck].update(cards)
    return [
        f"{deck_label(deck, owners)}: {', '.join(sorted(cards))}"
        for deck, cards in sorted(weak.items())
        if cards
    ]
