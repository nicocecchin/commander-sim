# commander-sim

Headless simulation of 4-player Magic: The Gathering Commander games (Forge AI vs Forge AI) to
evaluate decklists. Early development; see `CLAUDE.md` for goals and milestones and `NOTES.md`
for everything learned about Forge.

Results measure "deck as piloted by the Forge AI", which is heuristic and plays combo decks
poorly.

## Requirements

- Java 21 (tested with OpenJDK 21) available on `PATH` as `java`
- [uv](https://docs.astral.sh/uv/)

| OS | Java | uv |
|---|---|---|
| Linux | `sudo apt install openjdk-21-jre-headless` (or your distro's package) | `pipx install uv` or the official installer |
| macOS | `brew install openjdk@21` | `brew install uv` |
| Windows | `winget install EclipseAdoptium.Temurin.21.JRE` | `winget install astral-sh.uv` |

Only Linux has been tested so far.

## Setup

```bash
uv sync
uv run commander-sim forge setup   # downloads the pinned Forge release (~300 MB) into vendor/forge/
```

## Tests

```bash
uv run pytest                      # fast unit tests
uv run pytest -m integration       # slow: runs real Forge games (about 3 minutes)
uv run ruff check . && uv run ruff format --check .
```
