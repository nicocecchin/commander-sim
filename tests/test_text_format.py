import pytest

from commander_sim.decks.model import DeckCard
from commander_sim.decks.text_format import DeckParseError, parse_deck_text


def parse(text: str, commanders=()):
    return parse_deck_text(text, "d", lambda name: name in commanders)


def names(cards):
    return [card.name for card in cards]


def test_plain_list_with_counts_and_comments():
    deck = parse("// my deck\n1 Sol Ring\n3x Forest\n\n# note\n1 Lightning Bolt\n")
    assert deck.main == (DeckCard("Sol Ring"), DeckCard("Forest", 3), DeckCard("Lightning Bolt"))
    assert deck.commanders == ()


def test_commander_header_and_ignored_sideboard():
    text = "Commander\n1 Atraxa\n\nDeck\n1 Sol Ring\n\nSideboard\n1 Swords\n"
    deck = parse(text)
    assert names(deck.commanders) == ["Atraxa"]
    assert names(deck.main) == ["Sol Ring"]


def test_archidekt_categories_set_codes_and_tags():
    text = (
        "1x Atraxa, Praetors' Voice (cm2) 41 [Commander{top}]\n"
        "1x Sol Ring (c21) 263 [Ramp,Artifact] ^Have,#37d67a^\n"
        "2x Forest (znr) 280 *F*\n"
    )
    deck = parse(text)
    assert names(deck.commanders) == ["Atraxa, Praetors' Voice"]
    assert deck.main == (DeckCard("Sol Ring"), DeckCard("Forest", 2))


def test_moxfield_style_trailing_block_is_the_commander_when_eligible():
    text = "1 Sol Ring (C21) 263\n1 Forest (ZNR) 280\n\n1 Atraxa, Praetors' Voice (CM2) 41\n"
    deck = parse(text, commanders={"Atraxa, Praetors' Voice"})
    assert names(deck.commanders) == ["Atraxa, Praetors' Voice"]
    assert names(deck.main) == ["Sol Ring", "Forest"]


def test_trailing_block_is_not_taken_when_not_eligible():
    deck = parse("1 Sol Ring\n\n1 Forest\n")
    assert deck.commanders == ()
    assert names(deck.main) == ["Sol Ring", "Forest"]


def test_split_card_names_survive():
    assert names(parse("1 Fire // Ice (MMA) 1\n").main) == ["Fire // Ice"]


def test_unrecognised_line_is_an_error_not_silently_dropped():
    with pytest.raises(DeckParseError, match="Sol Ring"):
        parse("Sol Ring\n")
