"""Who controls a seat. Forge AI is the only pilot for now."""

from enum import StrEnum


class Pilot(StrEnum):
    FORGE_AI = "forge_ai"
