# commander-sim
 
Tool for simulating large numbers of **Magic: The Gathering Commander** games (AI vs AI) using
**Forge** in headless sim mode, to produce statistically meaningful data for evaluating decklists
for a small playgroup.
 
This repo will later serve as the **evaluation harness** for a custom MTG-playing model developed
in a separate project. Keep that in mind when designing interfaces (see "Player abstraction").
 
## Goals
 
1. Run thousands of 4-player Commander games headless, in parallel, unattended.
2. Import decklists (Moxfield / Archidekt exports, plain text) and convert them to Forge `.dck`.
3. Validate decks: flag cards Forge does not implement **before** running anything.
4. Store every game result in a database and compute honest statistics.
5. Compare deck variants (A/B) against a fixed field of opponent decks.
6. Later: a "goldfish" module (solitaire Monte Carlo) for consistency metrics.
## Non-goals (for now)
 
- Human vs human / human vs AI online play. That comes later and will likely use XMage or Forge
  network play; do not build networking now, but don't make design choices that prevent it.
- Training models. GPU work belongs to the separate research project.
- A GUI. CLI first; a simple static HTML report is fine.
## Context about the playgroup
 
- 5-6 players, mostly playing **recent preconstructed decks**, including some from very new sets
  and Universes Beyond (e.g. TMNT). Forge's card support for brand-new sets lags behind, so
  **unimplemented cards are expected**. Deck validation is a first-class feature, not an afterthought.
- Decks in a pod are typically similar power level (precons), so A/B testing variants of a deck
  against the group's real decks is the main use case.
## Hardware and environments
 
| Machine | CPU | RAM | Role |
|---|---|---|---|
| Dev laptop | Ryzen 5 5600H (6C/12T) | 16 GB | development, small runs |
| Run box (`pino`, shared) | AMD Ryzen 9 5900X (20 threads visible) | 60 GB | large unattended runs, in Docker |
 
- Both run Linux. **Code must stay cross-platform** (Linux, Windows, macOS) because other players
  will eventually run it.
- The run box has an RTX 4090, but Forge simulation is CPU-only. Do not add GPU dependencies here.
- Each Forge JVM loads the full card database and is memory-hungry. The worker count must be
  derived from **both** CPU cores and a RAM budget (`workers = min(cores - 1, ram_budget / heap_per_worker)`),
  and both must be configurable. Measure the actual per-JVM memory early (milestone 1) and record it
  in `NOTES.md`; don't guess.
- Remote runs: the run box is reached over SSH. A run must be fully described by a job file plus
  deck files, so it can be copied to another machine, executed there, and its results merged back.
## Tech stack
 
- **Python 3.11+**, managed with `uv`. Package code under `src/commander_sim/`.
- CLI: `typer`. Config/job specs: YAML validated with `pydantic`.
- Storage: **SQLite** (one DB per run, plus a merge command). No server databases.
- Stats: `numpy` / `scipy`; `trueskill` (or `openskill`) for multiplayer ratings.
- Tests: `pytest`. Lint/format: `ruff`.
- Forge: a **pinned version**, downloaded by a setup command into a local `vendor/forge/`
  directory (gitignored). Record the version in config so results are reproducible.
- Java: call `java -jar <forge-jar> sim ...` directly via `subprocess`. Do **not** rely on
  `forge.sh` or `forge.exe` (on Windows `forge.exe` sends output only to the log file).
- Optional later: a `Dockerfile` (JDK + pinned Forge + this package) for the run box and other OSes.
### Cross-platform rules
 
- Use `pathlib` everywhere; never hardcode `/` separators or `~`.
- No shell scripts as the primary interface; everything goes through the Python CLI.
  `subprocess` calls take argument lists, never `shell=True`.
- Use `multiprocessing` / `concurrent.futures` in a way that works with the `spawn` start method
  (Windows/macOS default).
- Use `platformdirs` for user data/cache locations.
## Forge sim mode: known facts
 
From the Forge wiki (`https://github.com/Card-Forge/forge/wiki/ai`):
 
```
sim -d <deck1> ... <deckN> -D [path] -n [N] -m [M] -f [F] -t [T] -p [P] -q -c [S]
```
 
- `-d` deck files or names; `-D` absolute path to a deck folder; `-n` number of games;
  `-m` best-of-M; `-f Commander` format; `-t Bracket|RoundRobin|Swiss` tournament; `-p` players per
  pairing in tournaments; `-q` quiet (results only); `-c` max seconds per match before a draw
  (default 120, **far too low for Commander**, make it configurable and default much higher).
**Must be verified empirically (milestone 1) and documented in `NOTES.md`:**
- Exact stdout format of results (winner line, turn count, draw/timeout).
- Whether deck order in `-d` determines turn order / seat.
- Whether games can be seeded for reproducibility.
- Where Forge looks for its user data dir on each OS, and how to point it at a custom one so
  parallel workers don't interfere.
- How Forge reports unimplemented or unrecognized cards on deck load.
- Per-JVM memory usage and average game duration for a 4-player Commander game.
Known AI limitations (from the wiki): heuristic, not trained; plays aggro/midrange best,
control poorly-to-OK, **most combo decks badly**. Results measure "deck as piloted by Forge AI".
Reports must state this.
 
## Statistics rules
 
- Always report winrate **with a 95% confidence interval** and the number of games.
- In a 4-player pod the baseline winrate is 25%. ~1000+ games per configuration are needed to
  resolve differences of ~5 points. The CLI should warn when sample sizes are too small for the
  comparison asked.
- **Rotate seats**: every deck must play every seat position equally often.
- Track draws/timeouts separately; never silently count them as losses.
- A/B comparisons: variant A and variant B must face the **same opponent field** with the same
  seat distribution.
- Record per game: run id, Forge version, seed (if available), decks by seat, winner, turn of win,
  elimination order (if parseable), duration, outcome type (win/draw/timeout/crash).
## Player abstraction
 
Forge AI is the only pilot for now, but design the runner around a `Pilot` concept
(e.g. `forge_ai`), recorded per seat in the results. A future custom model will be plugged in as
another pilot type. Don't over-engineer it: an enum plus a field in the DB is enough today.
 
## Milestones (do them in order, commit after each)
 
1. **Spike**: run one 4-player Commander game headless with 4 sample decks; parse the result;
   fill in the "must be verified" list in `NOTES.md`.
2. **Runner**: parallel workers, isolated Forge user dirs per worker, seat rotation, timeouts,
   crash recovery, resumable runs, progress output.
3. **Deck import + validation**: Moxfield/Archidekt/plain text to `.dck`; commander detection;
   report unimplemented/unknown cards; refuse to run invalid decks unless `--allow-invalid`.
4. **Storage + stats**: SQLite schema, `merge` command, winrate + CI, A/B comparison, ratings.
5. **Report**: a static HTML report per run.
6. **Remote runs**: job files, a documented workflow for running on the run box over SSH
   and pulling results back. Optional Dockerfile.
7. **Goldfish module**: fast solitaire simulation (mulligans, land drops, mana development,
   turn the commander is cast, probability of key cards by turn N).
## How to work in this repo
 
- Before starting a milestone, propose a short plan and wait for approval.
- **Run things and check the output.** Don't claim something works without having executed it.
- Write tests for parsers, deck conversion and stats. Use small recorded Forge outputs as fixtures
  rather than running Forge in unit tests; keep a separate, slow integration test that does run Forge.
- Keep `NOTES.md` up to date with every Forge quirk discovered (log formats, CLI bugs, slow cards,
  memory numbers). The separate research project reads this file, so write it for an outsider.
- Keep `README.md` current with install and usage instructions for all three OSes.
- Small, focused commits with clear messages.
- Ask before adding heavy dependencies.
- **Commits carry no AI attribution.** Never add `Co-Authored-By` lines (or any other
  mention of Claude/AI) to commit messages or PR descriptions. The user is the sole author.
- **Clean, modular, reusable code.** Small single-purpose modules and functions with clear
  interfaces, designed so they can be reused (the runner, parsers and stats are reused by the
  later model-evaluation project). No junk: no dead code, commented-out code, unused
  parameters, speculative hooks or leftover scaffolding. When a change makes code obsolete,
  delete it in the same change. Prefer extending an existing helper over duplicating logic.
## Directory layout (target)
 
```
commander-sim/
  CLAUDE.md
  NOTES.md            # Forge findings, measured numbers
  README.md
  pyproject.toml
  src/commander_sim/
    cli.py
    config.py         # pydantic models for job files
    forge/            # setup/download, invocation, output parsing
    decks/            # import, conversion, validation
    runner/           # scheduling, workers, seat rotation
    storage/          # SQLite schema, merge
    stats/            # winrates, CIs, A/B, ratings
    report/           # HTML report
    goldfish/         # later
  decks/              # playgroup decks (source lists + generated .dck)
  jobs/               # example job files
  runs/               # outputs (gitignored)
  vendor/forge/       # pinned Forge install (gitignored)
  tests/
```
 