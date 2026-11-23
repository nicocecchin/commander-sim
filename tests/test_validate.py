from commander_sim.decks.model import Deck, DeckCard
from commander_sim.decks.validate import Severity, validate_deck
from tests.card_scripts import make_index

INDEX = make_index(
    "sol_ring",
    "forest",
    "lightning_bolt",
    "thrasios",
    "tymna",
    "atraxa",
    "toxic_deluge",
    "relentless_rats",
    "breeding_pool",
)


def deck(commanders: list[str], main: dict[str, int], fill: bool = True) -> Deck:
    """A deck padded with Forests to 100 cards, unless `fill` is False."""
    cards = [DeckCard(name, count) for name, count in main.items()]
    deck = Deck("d", tuple(DeckCard(n) for n in commanders), tuple(cards))
    if fill:
        padding = 100 - deck.size
        cards.append(DeckCard("Forest", padding))
        deck = Deck("d", deck.commanders, tuple(cards))
    return deck


def messages(report, severity: Severity) -> list[str]:
    return [i.message for i in report.issues if i.severity is severity]


def test_valid_deck_has_no_errors():
    report = validate_deck(deck(["Thrasios, Triton Hero"], {"Sol Ring": 1}), INDEX)
    assert report.ok
    assert report.issues == ()


def test_unknown_card_is_an_error_with_suggestion():
    report = validate_deck(deck(["Thrasios, Triton Hero"], {"Sol Rng": 1}), INDEX)
    assert not report.ok
    assert "Unknown card 'Sol Rng' (did you mean: Sol Ring?)" in messages(report, Severity.ERROR)


def test_wrong_size():
    report = validate_deck(deck(["Atraxa, Praetors' Voice"], {"Sol Ring": 1}, fill=False), INDEX)
    assert any("expected 100" in m for m in messages(report, Severity.ERROR))


def test_missing_commander():
    report = validate_deck(deck([], {"Sol Ring": 1}), INDEX)
    assert "No commander found" in messages(report, Severity.ERROR)


def test_non_legendary_commander():
    report = validate_deck(deck(["Sol Ring"], {"Lightning Bolt": 1}), INDEX)
    assert "'Sol Ring' cannot be a commander" in messages(report, Severity.ERROR)


def test_partners_are_allowed_but_not_unpaired_pairs():
    ok = validate_deck(deck(["Thrasios, Triton Hero", "Tymna the Weaver"], {}), INDEX)
    assert ok.ok
    bad = validate_deck(deck(["Thrasios, Triton Hero", "Atraxa, Praetors' Voice"], {}), INDEX)
    assert any("cannot be paired" in m for m in messages(bad, Severity.ERROR))


def test_singleton_rule_exempts_basics_and_any_number_cards():
    report = validate_deck(
        deck(["Atraxa, Praetors' Voice"], {"Lightning Bolt": 2, "Relentless Rats": 9}), INDEX
    )
    assert messages(report, Severity.ERROR) == ["2 copies of 'Lightning Bolt' (singleton format)"]


def test_duplicate_through_alias_names_is_counted_once_per_card():
    report = validate_deck(deck(["Atraxa, Praetors' Voice"], {"sol ring": 1, "Sol Ring": 1}), INDEX)
    assert "2 copies of 'Sol Ring' (singleton format)" in messages(report, Severity.ERROR)


def test_colour_identity_violation_is_a_warning():
    report = validate_deck(deck(["Thrasios, Triton Hero"], {"Lightning Bolt": 1}), INDEX)
    assert report.ok
    assert messages(report, Severity.WARNING) == [
        "'Lightning Bolt' has colours outside the commander's identity (R)"
    ]


def test_ai_weak_cards_are_warned_about():
    report = validate_deck(deck(["Atraxa, Praetors' Voice"], {"Toxic Deluge": 1}), INDEX)
    assert report.ok
    assert "Toxic Deluge" in messages(report, Severity.WARNING)[0]
