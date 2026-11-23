"""Who owns which deck. Optional; only used to label results."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

DEFAULT_PLAYGROUP_FILE = Path("decks") / "playgroup.yaml"


class Playgroup(BaseModel):
    """`players` maps a player name to the deck file names they own."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    players: dict[str, tuple[str, ...]]

    def owners(self) -> dict[str, str]:
        return {deck: player for player, decks in self.players.items() for deck in decks}


def load_owners(path: Path) -> dict[str, str]:
    """Deck file name -> owner, or an empty mapping if the file does not exist."""
    if not path.is_file():
        return {}
    return Playgroup.model_validate(yaml.safe_load(path.read_text(encoding="utf-8"))).owners()
