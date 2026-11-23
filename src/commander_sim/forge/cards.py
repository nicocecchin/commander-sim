"""Index of the cards Forge has scripts for, built from its card database."""

import difflib
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

CARDS_ZIP = Path("res") / "cardsfolder" / "cardsfolder.zip"
AI_WEAK_FLAG = "All"  # `AI:RemoveDeck:All`: Forge says its AI plays this card badly

_FACE_SEPARATOR = "\nALTERNATE\n"
_COLORS = "WUBRG"
_COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_BASIC_LAND_TYPES = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}
_PAIRING_KEYWORDS = ("K:Partner", "K:Choose a Background", "K:Doctor's companion")
_ANY_NUMBER = "a deck can have any number"
_REMINDER_TEXT = re.compile(r"\([^)]*\)")
_SYMBOL = re.compile(r"\{([^}]*)\}")


def normalize_name(name: str) -> str:
    """Lowercase, strip accents and unify quotes and spacing, for forgiving name matching."""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    unified = stripped.replace("’", "'").replace("‘", "'")
    return " ".join(unified.lower().split())


@dataclass(frozen=True)
class CardInfo:
    name: str  # the name to write in a Forge deck file
    color_identity: frozenset[str]
    ai_flags: frozenset[str]
    is_basic_land: bool
    can_be_commander: bool
    is_background: bool
    has_pairing_keyword: bool
    allows_any_number: bool


def _fields(face: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for line in face.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields.setdefault(key, []).append(value)
    return fields


def _identity_of_face(fields: dict[str, list[str]], types: str) -> set[str]:
    colors = {c for c in "".join(fields.get("ManaCost", [""])) if c in _COLORS}
    for value in fields.get("Colors", []):
        colors |= {_COLOR_WORDS[w] for w in value.split(",") if w in _COLOR_WORDS}
    colors |= {c for word, c in _BASIC_LAND_TYPES.items() if word in types.split()}
    oracle = " ".join(fields.get("Oracle", []))
    if "Basic" not in types and not any(w in types.split() for w in _BASIC_LAND_TYPES):
        oracle = _REMINDER_TEXT.sub("", oracle)
    for symbol in _SYMBOL.findall(oracle):
        colors |= {c for c in symbol if c in _COLORS}
    return colors


def _is_commander_eligible(types: list[str], has_power_toughness: bool) -> bool:
    """Legendary creatures, and legendary Vehicles or Spacecraft that have power and toughness."""
    if "Legendary" not in types:
        return False
    return "Creature" in types or (
        has_power_toughness and ("Vehicle" in types or "Spacecraft" in types)
    )


def parse_card_script(script: str) -> tuple[CardInfo, tuple[str, ...]]:
    """Return the card and the names of its faces (front face first)."""
    faces = [_fields(face) for face in script.split(_FACE_SEPARATOR)]
    # A face may be a copy of another card's face; its colours are then not known here, which can
    # only make the colour-identity check miss something, never invent a violation.
    face_names = tuple((f.get("Name") or f["CopyFaceFrom"])[0].strip() for f in faces)
    front = faces[0]
    types = {i: " ".join(f.get("Types", [""])) for i, f in enumerate(faces)}
    is_split = "Split" in front.get("AlternateMode", [])
    identity: set[str] = set()
    for index, face in enumerate(faces):
        identity |= _identity_of_face(face, types[index])
    lines = [
        line
        for face in faces
        for key, vals in face.items()
        for line in (f"{key}:{v}" for v in vals)
    ]
    oracle = " ".join(" ".join(f.get("Oracle", [])) for f in faces).lower()
    flags = {line.split(":")[2] for line in lines if line.startswith("AI:RemoveDeck:")}
    card = CardInfo(
        name=" // ".join(face_names) if is_split else face_names[0],
        color_identity=frozenset(identity),
        ai_flags=frozenset(flags),
        is_basic_land="Basic" in types[0].split(),
        can_be_commander=_is_commander_eligible(types[0].split(), "PT" in front)
        or "can be your commander" in oracle,
        is_background="Background" in types[0].split(),
        has_pairing_keyword=any(line.startswith(_PAIRING_KEYWORDS) for line in lines),
        allows_any_number=_ANY_NUMBER in oracle,
    )
    return card, face_names


class CardIndex:
    def __init__(self) -> None:
        self._by_key: dict[str, CardInfo] = {}

    def add(self, card: CardInfo, face_names: tuple[str, ...]) -> None:
        for name in {card.name, *face_names}:
            self._by_key.setdefault(normalize_name(name), card)

    def __len__(self) -> int:
        return len(self._by_key)

    def lookup(self, name: str) -> CardInfo | None:
        return self._by_key.get(normalize_name(name))

    def suggest(self, name: str, limit: int = 3) -> list[str]:
        """Names close to `name`, for "did you mean" hints."""
        keys = difflib.get_close_matches(normalize_name(name), self._by_key, n=limit, cutoff=0.75)
        return [self._by_key[key].name for key in keys]


def load_card_index(forge_dir: Path) -> CardIndex:
    index = CardIndex()
    with zipfile.ZipFile(forge_dir / CARDS_ZIP) as archive:
        for entry in archive.namelist():
            if entry.endswith(".txt"):
                script = archive.read(entry).decode("utf-8", errors="replace")
                index.add(*parse_card_script(script))
    return index
