from commander_sim.forge.cards import normalize_name, parse_card_script
from tests.card_scripts import SCRIPTS, make_index


def card(key: str):
    return parse_card_script(SCRIPTS[key])[0]


def test_normalize_name_ignores_case_accents_quotes_and_spacing():
    assert normalize_name("  Jötun   Grunt ") == "jotun grunt"
    assert normalize_name("Atraxa, Praetors’ Voice") == "atraxa, praetors' voice"


def test_color_identity_from_cost_indicator_and_land_types():
    assert card("sol_ring").color_identity == frozenset()
    assert card("forest").color_identity == {"G"}
    assert card("breeding_pool").color_identity == {"G", "U"}
    assert card("fire_ice").color_identity == {"R", "U"}
    assert card("delver").color_identity == {"U"}


def test_split_cards_are_named_with_both_halves_and_found_by_either():
    index = make_index("fire_ice", "delver")
    assert index.lookup("Ice").name == "Fire // Ice"
    assert index.lookup("fire // ice").name == "Fire // Ice"
    assert index.lookup("Insectile Aberration").name == "Delver of Secrets"


def test_commander_eligibility():
    assert card("thrasios").can_be_commander
    assert card("inspirit").can_be_commander
    assert not card("legendary_equipment").can_be_commander
    assert not card("sol_ring").can_be_commander
    assert card("thrasios").has_pairing_keyword
    assert not card("atraxa").has_pairing_keyword


def test_flags():
    assert card("toxic_deluge").ai_flags == {"All"}
    assert card("forest").is_basic_land
    assert not card("breeding_pool").is_basic_land
    assert card("relentless_rats").allows_any_number


def test_script_with_copied_faces_still_gets_a_name():
    info, faces = parse_card_script(SCRIPTS["bind_liberate"])
    assert faces == ("Bind", "Liberate")
    assert info.name == "Bind // Liberate"


def test_suggest_close_names():
    index = make_index("sol_ring", "lightning_bolt")
    assert index.suggest("Sol Rng") == ["Sol Ring"]
    assert index.suggest("Completely Different") == []
