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

## Decks

Decks live as Forge `.dck` files (`decks/playgroup/` holds the playgroup's precons).

```bash
# Convert a Moxfield / Archidekt / plain-text export (paste the export into a text file first)
uv run commander-sim decks import my-list.txt --name "My Deck" --out-dir decks/imported
# Copy one of the precon lists that ship with Forge
uv run commander-sim decks import-precon "Temur Roar" "Counter Blitz" --out-dir decks/playgroup
# Check decks without running anything (.dck files, folders, or text lists)
uv run commander-sim decks validate decks/playgroup
```

Validation errors: unknown cards (with suggestions), wrong deck size, missing or illegal
commander, duplicates. Warnings: colour identity and cards Forge flags as badly played by its AI.
Loading Forge's card database takes about 7 seconds per command.

## Running simulations

A job file names a folder of `.dck` decks, a **matchup** and a game count. Seats are rotated so
every deck sits in every seat equally often; the CLI warns if your game count does not allow that.

```yaml
matchup: {kind: pod, decks: [a.dck, b.dck, c.dck, d.dck]}   # the same 4 decks every game
matchup: {kind: league, decks: [... 4 or more decks]}        # every 4-deck pod; for ratings
matchup:                                                      # A/B test of two variants
  kind: ab
  variants: [my-deck-a.dck, my-deck-b.dck]
  field: [x.dck, y.dck, z.dck, w.dck]                         # opponents, at least 3
```

In an A/B job the two variants face the **same opponents, in the same seats, with the same seed**;
`games` is split equally between them. See `jobs/` for examples.

```bash
uv run commander-sim run jobs/playgroup-smoke.yaml
```

Every deck is validated first and the run is refused if one is invalid (add `--allow-invalid` to
override). Warnings, such as cards Forge says its AI plays badly, are always shown. Results go to
`runs/<job name>/results.sqlite`. Press Ctrl+C to stop; running the same command again resumes
where it left off. The worker count is `min(cores - 1, RAM budget / heap)`; set `workers.max` or
`workers.ram_budget_gb` in the job file to override it.

## Results

```bash
uv run commander-sim stats runs/playgroup-league/results.sqlite     # winrates, seats, ratings
uv run commander-sim compare runs/ab/results.sqlite --a my-deck-a.dck --b my-deck-b.dck
uv run commander-sim merge all.sqlite runs/one/results.sqlite runs/two/results.sqlite
```

- Winrates are wins divided by games that had a winner, with a 95% Wilson interval. Timeouts are
  shown separately and crashes are never counted as losses.
- `compare` gives the difference with a 95% interval and p-value, says how small a difference the
  sample can detect, and warns when the two decks did not face the same field or seats. About
  1000 decided games per deck are needed to resolve a 5-point difference.
- Win length is shown as turns (every player's turn counted) and rounds (one pass around the
  table). Both come from the full game log, because Forge's own `Turn N` result line is about
  half the real turn count in games with more than 2 players.
- Ratings are a Plackett-Luce fit on who won each pod ("expected winrate against three reference
  decks"), with bootstrap intervals.
- Every `run` writes `runs/<job>/report.html` when it finishes. `report` builds one from any
  databases, including merged ones:

  ```bash
  uv run commander-sim report runs/playgroup-league/results.sqlite --out league.html
  ```

  The report is a single offline HTML file (inline charts, light and dark mode, phone friendly):
  deck winrates with intervals, the A/B result when the job was an A/B test, ratings, seat
  winrates, game length and speed, and a data-quality section (crashed tasks, decks whose card
  list changed, a seat-balance grid, cards Forge says its AI plays badly).
- `decks/playgroup.yaml` maps players to decks and labels the tables. Results always carry the
  reminder that they measure decks as piloted by the Forge AI.
- `merge` and `stats` accept several databases (for example runs from the run box); a run
  cannot appear twice.

## Running on another machine (run box)

Long runs go to a remote Linux machine with Docker, so nothing has to be installed there
besides Docker. Commands run from your laptop over `ssh`/`scp` (key login must already work):

```bash
export COMMANDER_SIM_HOST=user@runbox.example.org     # or pass --host; a ~/.ssh/config alias works
uv run commander-sim remote run jobs/precon-four.yaml --workers 10
uv run commander-sim remote status precon-four
uv run commander-sim remote fetch precon-four           # snapshot + report into runs/precon-four@runbox/
uv run commander-sim remote stop precon-four            # clean stop; `remote run` again resumes
```

- `remote run` ships the **committed** code (it refuses uncommitted changes), builds the image
  `commander-sim:<commit>` on the remote if it is not there yet, uploads a bundle (job file and
  its decks) and starts a detached container. Decks travel by `scp`, never through git.
- **Checkpoints and recovery:** every finished Forge launch is saved to the run's SQLite
  database at once, so a crash loses only the games in progress (with `games_per_task: 1`, one
  game per worker). A Forge process that dies is retried inside the run, and if the runner
  itself fails Docker restarts the container (up to 5 times) and it resumes. If the container
  was stopped or killed by someone, or the machine rebooted, `remote status` says so and
  `remote run` with the same job file resumes from the saved games.
- `remote watchdog install` adds a cron entry on the remote that does that resume every 10
  minutes for any unfinished job not stopped with `remote stop` (`remote watchdog remove` undoes
  it; other cron entries are left alone).
- `--workers` caps the Forge processes; the container also gets `workers + 1` CPUs and
  `2 GB x workers` of memory, so the run cannot take over a shared machine.
- `remote fetch` is safe while the job is running. Use `stats`, `compare` or `merge` on the
  fetched database like any other.
- Without the `remote` commands, on any machine with Docker: `docker build -t commander-sim .`,
  put a job file and its decks in `work/bundle/`, then
  `docker run -d -v "$PWD/work:/work" commander-sim run /work/bundle/job.yaml --runs-dir /work/runs`.

## Tests

```bash
uv run pytest                      # fast unit tests
uv run pytest -m integration       # slow: runs real Forge games (about 3 minutes)
uv run ruff check . && uv run ruff format --check .
```
