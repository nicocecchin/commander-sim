from pathlib import Path

from commander_sim.decks.dck_format import read_dck, write_dck
from commander_sim.decks.model import Deck, DeckCard

FORGE_PRECON = """[metadata]
Name=Turtle Power! [TMC] [2026]
[Commander]
1 Leonardo, the Balance|TMC|1
1 Michelangelo, the Heart|TMC|1
[Main]
1 Sol Ring|C21|263
12 Forest|ZNR
[Sideboard]
1 Ignored Card|XXX
"""


def test_reads_forge_precon_format(tmp_path: Path):
    path = tmp_path / "p.dck"
    path.write_text(FORGE_PRECON, encoding="utf-8")
    deck = read_dck(path)
    assert deck.name == "Turtle Power! [TMC] [2026]"
    assert [c.name for c in deck.commanders] == ["Leonardo, the Balance", "Michelangelo, the Heart"]
    assert deck.main == (DeckCard("Sol Ring"), DeckCard("Forest", 12))


def test_write_then_read_round_trips_without_set_codes(tmp_path: Path):
    deck = Deck("Mine", (DeckCard("Atraxa"),), (DeckCard("Sol Ring"), DeckCard("Forest", 5)))
    path = tmp_path / "out" / "mine.dck"
    write_dck(deck, path)
    assert "|" not in path.read_text(encoding="utf-8")
    assert read_dck(path) == deck
