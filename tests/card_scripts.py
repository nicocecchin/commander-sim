"""Small Forge card scripts for building card indexes in tests."""

import zipfile
from pathlib import Path

from commander_sim.forge.cards import CARDS_ZIP, CardIndex, parse_card_script

SCRIPTS = {
    "sol_ring": "Name:Sol Ring\nManaCost:1\nTypes:Artifact\nOracle:{T}: Add {C}{C}.\n",
    "forest": "Name:Forest\nManaCost:no cost\nTypes:Basic Land Forest\nOracle:({T}: Add {G}.)\n",
    "breeding_pool": (
        "Name:Breeding Pool\nManaCost:no cost\nTypes:Land Forest Island\n"
        "Oracle:({T}: Add {G} or {U}.)\n"
    ),
    "fire_ice": (
        "Name:Fire\nManaCost:1 R\nTypes:Instant\nAlternateMode:Split\nOracle:Fire deals 2.\n"
        "\nALTERNATE\n\n"
        "Name:Ice\nManaCost:1 U\nTypes:Instant\nOracle:Tap target permanent.\n"
    ),
    "delver": (
        "Name:Delver of Secrets\nManaCost:U\nTypes:Creature Human Wizard\nPT:1/1\n"
        "AlternateMode:DoubleFaced\nOracle:Transform.\n"
        "\nALTERNATE\n\n"
        "Name:Insectile Aberration\nManaCost:no cost\nColors:blue\nTypes:Creature Human Insect\n"
        "PT:3/2\nOracle:Flying\n"
    ),
    "thrasios": (
        "Name:Thrasios, Triton Hero\nManaCost:G U\nTypes:Legendary Creature Merfolk Wizard\n"
        "PT:1/3\nK:Partner\nOracle:Scry 1. Partner (You can have two commanders.)\n"
    ),
    "tymna": (
        "Name:Tymna the Weaver\nManaCost:1 W B\nTypes:Legendary Creature Human Cleric\n"
        "PT:2/2\nK:Partner\nOracle:Lifelink. Partner\n"
    ),
    "atraxa": (
        "Name:Atraxa, Praetors' Voice\nManaCost:G W U B\nTypes:Legendary Creature Phyrexian Angel\n"
        "PT:4/4\nOracle:Flying, vigilance, deathtouch, lifelink\n"
    ),
    "inspirit": (
        "Name:Inspirit, Flagship Vessel\nManaCost:U R W\nTypes:Legendary Artifact Spacecraft\n"
        "PT:5/5\nOracle:Station.\n"
    ),
    "legendary_equipment": (
        "Name:Sword of Fire\nManaCost:3\nTypes:Legendary Artifact Equipment\nOracle:Equip.\n"
    ),
    "toxic_deluge": (
        "Name:Toxic Deluge\nManaCost:2 B\nTypes:Sorcery\nAI:RemoveDeck:All\n"
        "Oracle:Pay any amount of life.\n"
    ),
    "relentless_rats": (
        "Name:Relentless Rats\nManaCost:1 B\nTypes:Creature Rat\nPT:2/2\n"
        "Oracle:A deck can have any number of cards named Relentless Rats.\n"
    ),
    "lightning_bolt": "Name:Lightning Bolt\nManaCost:R\nTypes:Instant\nOracle:3 damage.\n",
    "bind_liberate": (
        "CopyFaceFrom:Bind\nAlternateMode:Split\n\nALTERNATE\n\nCopyFaceFrom:Liberate\n"
    ),
}


def make_index(*keys: str) -> CardIndex:
    index = CardIndex()
    for key in keys:
        index.add(*parse_card_script(SCRIPTS[key]))
    return index


def write_forge_dir(forge_dir: Path, *keys: str) -> None:
    """Create a minimal fake Forge install holding a card database with the given scripts."""
    zip_path = forge_dir / CARDS_ZIP
    zip_path.parent.mkdir(parents=True)
    with zipfile.ZipFile(zip_path, "w") as archive:
        for key in keys:
            archive.writestr(f"{key[0]}/{key}.txt", SCRIPTS[key])
