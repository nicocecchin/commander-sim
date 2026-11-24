# Forge findings (milestone 1 spike)

Everything here was verified empirically against **Forge 2.0.16** (release `forge-2.0.16`,
build 2026-11-11) on Linux with OpenJDK 21, unless marked *unverified*. Test decks: the five
mono-colour starter Commander decks shipped inside Forge
(`res/adventure/common/decks/starter/commander/*.dck`). Real playgroup precons will be slower
and may behave differently; re-measure when they are imported.

## Invocation

```
cd <forge dir>          # REQUIRED: Forge resolves res/ relative to the cwd
java -Xmx1536m -Duser.home=<worker home> -jar forge-gui-desktop-2.0.16-jar-with-dependencies.jar \
     sim -d d1.dck d2.dck d3.dck d4.dck -D <abs deck dir> -f Commander -n N -c SECONDS -q [-s SEED]
```

- Running from any other cwd fails with `MissingResourceException: Can't find bundle for base
  name en-US` and exit code 0. The runner must set `cwd` to the Forge dir.
- Full option list (from the jar): `-d -D -n -m -t -p -f -s -a -mc -c -q`.
  `-s` = RNG seed, `-a` = AI profile per player, `-mc` = Monte Carlo AI refinement (off by
  default in sim), `-c` = per-match clock in seconds (default 120).
- Without `-q` the output is the full game log (2000+ lines for one game). With `-q` only the
  result block is printed (no per-turn lines, hence no real turn count). Both start with ~20 lines of noise ("The card ... was not assigned to
  any set"); the parser ignores everything it does not recognise.
- `-D` must be an absolute path to a folder containing the deck files named in `-d`.
- Exit code is 0 even on failures (missing deck, wrong cwd); success is judged by parsing the
  output, not by the exit code.

## Output format (`-q`)

```
Simulation mode
Ai(1)-<deck name> vs Ai(2)-<deck name> vs ... - one game of Commander seed 42
Game Outcome: Match Duration 1m : 25s
Game Outcome: Turn 34
Game Outcome: Ai(1)-<deck> has lost because life total reached 0
...
Game Outcome: Ai(4)-<deck> has won because all opponents have lost
Match Result: Ai(1)-<deck>: 0 ... Ai(4)-<deck>: 1

Game Result: Game 1 ended in 87011 ms. Ai(4)-<deck> has won!
```

- Header says `two games of Commander` etc. for `-n 2`; ` seed N` is appended only when `-s` is
  given. With several games the block from `Game Outcome` to `Game Result` repeats.
- Player label is `Ai(<seat>)-<deck name>`, where the deck name is the `Name=` in the `.dck`
  metadata, not the file name.
- **`Game Outcome: Turn N` (the only turn figure in `-q` output) is about half of the real turn
  counter.** Checked against the `Turn: Turn k (...)` lines of full logs in 4 games: 87 -> 44,
  42 -> 21, 53 -> 27, 68 -> 34. Cause (Forge source, `GameLogFormatter`): it prints
  `ceil(lastTurnNumber / 2.0)` with the comment "turn number counted from the starting player",
  which is a round count only in 2-player games. (Read from the current master branch on GitHub;
  the numbers match 2.0.16.)
- **So the runner does not use `-q`.** It parses the full log (about 130 KB per game): the last
  `Turn: Turn k` is the real turn count (every player's turn counted), and rounds are counted from
  the seat order of the `Turn:` lines (a new round starts when the order wraps past the starting
  player, so eliminated players do not inflate it; an extra turn counts as a new round). A seeded
  game gives the identical result with and without `-q` and takes the same time. The sim prints
  the whole log only when the game ends.
- Elimination order is **not** available in `-q` mode (loss lines are listed by seat). It would
  have to be parsed from the full log; not done.
- Win-by-commander-damage, decking etc. only appear in the loss reason text; *unverified* whether
  a true simultaneous-loss draw exists and what it prints.

## Seats, seeding, reproducibility

- **Seat = position in `-d`.** Seat 1 is the first deck; turn order follows seat order.
- The **starting player is randomised**, not always seat 1: an unseeded game started with seat 4,
  and with `-s 7` seat 1 started under two different deck orders. So seat rotation fixes turn
  *order* but not who goes first; record the starter if it turns out to matter (*unverified* how
  the seed drives it).
- `-s SEED` works: the same seed and decks gave the same winner and turn count twice
  (also across separate `user.home` dirs). Only the wall-clock duration differs. Seeds are echoed
  in the header. Reproducibility across Forge versions is not expected.

## User data and parallel isolation

- Forge writes preferences, `forge.log` and a card cache under `~/.forge/` and `~/.cache/forge/`
  (Linux). `forge.profile.properties` in the Forge dir can override these but it lives in the
  shared install, so it is no use for per-worker isolation.
- `-Duser.home=<dir>` redirects both (`<dir>/.forge`, `<dir>/.cache/forge`); verified on Linux.
  The Forge defaults on Windows come from `APPDATA`/`LOCALAPPDATA` and on macOS from
  `~/Library/...`; *unverified* whether `-Duser.home` is enough there. Check before milestone 2
  ships on those OSes.
- Concurrent JVMs with separate `user.home` ran without interference (3 at once).

## Unknown / unimplemented cards

- A card name Forge cannot find is **silently dropped from the deck**; the game still runs
  (verified with `Totally Fake Card`). Nothing is printed to stdout, with or without `-q`.
  The only trace is `<user.home>/.forge/forge.log`: `An unsupported card was requested: "<name>"`.
- Consequence: validation must be done **before** running, by checking card names against
  Forge's card scripts (`res/cardsfolder`) in milestone 3. Never rely on the sim to complain.
- Cards that exist but are only partially scripted are a separate problem; they cannot be
  detected this way (*unverified*, to be investigated with the real precons).

## Memory, CPU and speed (starter decks, 4 players)

| Measure | Result |
|---|---|
| Peak RSS per JVM (`-Xmx1024m`..`4096m`) | 0.7 - 1.0 GB |
| Smallest heap tried | `-Xmx1024m`: game completed, RSS 0.77 GB |
| JVM startup + card DB load | about 7 - 12 s before the first game |
| Game wall time, alone | 61 s (44 turns) |
| Game wall time, 2-3 JVMs at once | 31 - 87 s (31 - 35 turns) |
| CPU per JVM | roughly 1 - 1.5 cores busy (JIT/GC threads add to the game thread) |

Planning numbers for the worker formula: **budget 1.5 GB RSS per worker** (heap 1536 MB gives
headroom over the observed 1 GB peak) and `cores - 1` workers. On the 16 GB dev laptop with
about 6 GB free that is 3-4 workers. At about 60 s per game per worker, 1000 games take roughly
4-6 hours on the laptop; the numbers will move with real decks. Re-measure in milestone 2.

## Open items

- Behaviour of a real Forge crash / OOM (the runner's retry path is unit-tested with a fake
  Forge; only a manual `kill -9` of the whole run has been exercised for real).
- Windows/macOS user-dir isolation (see above). The runner also sets `APPDATA`/`LOCALAPPDATA`
  on Windows; untested there.
- Whether a genuine draw can occur besides timeouts.

## Runner measurements (milestone 2)

Dev laptop (12 threads, ~5 GB free RAM), starter decks, 2 workers, `-Xmx1536m`, one game per
Forge launch, 24 games (a real job would use 4 per launch, see `jobs/playgroup-smoke.yaml`):

| Measure | Result |
|---|---|
| Total RSS of the 2 JVMs | mean 1.46 GB, max 1.69 GB (about 0.85 GB each) |
| Game duration | mean 51 s, median 38 s, range 23 - 188 s |
| Game length | mean 27 turns as printed by Forge (about 54 real turns), range 18 - 41 |
| Throughput | 16 games in 444 s with 2 workers: about 130 games/hour |
| CPU | an end-to-end test with 2 workers used about 4.5 cores of CPU time, i.e. a JVM can use ~2 cores (JIT/GC) |
| Seat balance | each deck sat in each seat exactly 6 times in 24 games |
| Outcomes | 24 wins, 0 timeouts, 0 crashes |

- The CPU number suggests `cores - 1` workers may oversubscribe the CPU. Measure throughput with
  more workers on the run box before trusting the default formula.
- Interrupt and resume were exercised for real: `kill -9` of the runner (orphaned JVMs killed by
  hand) and Ctrl+C. After either, rerunning the same job skipped finished tasks and completed the
  rest. Ctrl+C kills the JVMs within a few seconds and leaves no orphan processes.
- Starting a Python process in the background of a non-interactive shell leaves SIGINT ignored,
  so Ctrl+C does nothing there; this only affects test harnesses, not interactive use.

## Card database and decks (milestone 3)

- Card scripts live in `res/cardsfolder/cardsfolder.zip` (about 35k files, one per card).
  `forge/cards.py` indexes them in about 7 s. Format: `Key:Value` lines, faces separated by a
  line `ALTERNATE`. Useful keys: `Name`, `ManaCost`, `Types`, `PT`, `Colors` (colour indicator),
  `K:` keywords, `Oracle`, `AlternateMode`, `AI:RemoveDeck:<All|Random|NonCommander>`.
- **Deck-file card names:** split cards (and rooms) are written `Fire // Ice`; adventure, modal
  and transforming cards use the front face name only (`Bonecrusher Giant`). The importer rewrites
  names to this form. Set codes in `.dck` lines are optional; we omit them.
- `AI:RemoveDeck:All` marks cards Forge's own deck builders exclude because its AI handles them
  badly. It does not stop the AI playing them when they are in a deck, so we report them as a
  warning ("played badly by its AI"). Unflagged cards may be handled badly too.
- **Commander eligibility** rule used by the validator: legendary creature, legendary Vehicle or
  Spacecraft with power and toughness, "can be your commander" in the Oracle text, or a
  Background. Pairs need a partner-style keyword (`K:Partner*`, `Choose a Background`,
  `Doctor's companion`) on both. The TMNT precon pairs Leonardo and Michelangelo through
  `Partner:Character select`.
- **Forge ships the playgroup's decks.** `res/quest/commanderprecons/*.dck` holds 184 Commander
  precon decklists up to the 2026 sets, including all 11 of the group's decks. Stock lists only:
  edited decks must be imported from an export.
- The text parsers were written from the known shapes of plain, Moxfield and Archidekt exports
  (counts, `(SET) number`, `[Category{top}]`, `*F*` and `^tag^` markers) and have not yet been
  tested on real exports. A Moxfield export with no commander header is handled by treating a
  final blank-line-separated block of one or two commander-eligible cards as the commanders.
- Colour identity is derived from mana costs, colour indicators, rules-text symbols and basic
  land types. Faces that copy another card's face (`CopyFaceFrom`, e.g. Bind // Liberate) are not
  resolved, so such cards can only be under-reported. It is a warning, not an error.

## Real precon speed (milestone 3 smoke run)

4 playgroup precons (Turtle Power!, Multiverse Reforged, Keen Engineering, Lorehold Spirit),
8 games, 2 workers, one game per launch, dev laptop. Outcomes: 8 wins, 0 timeouts, 0 crashes;
Forge's `forge.log` showed no unsupported-card messages.

| Measure | Result |
|---|---|
| Game duration | mean 252 s, median 151 s, range 20 - 913 s |
| Game length | mean 25 turns as printed by Forge (about 50 real turns), range 15 - 30 |
| Throughput | 8 games in 19 min with 2 workers: about 25 games/hour |
| CPU | 3075 s CPU time in 1135 s wall: about 2.7 cores for 2 workers |

**Real precons are about 5x slower than Forge's starter decks**, and durations vary 45x between
games. Long games are not long in turns; they are slow turns (AI deliberation on busy boards).
Plan capacity from the mean: 1000 games cost roughly 70 worker-hours, i.e. about 35 h on 2 laptop
workers or about 7 h on 10 workers. The `game_timeout_seconds` default (3600) was never reached;
the slowest game took 913 s.

`forge.log` also contained 16 `java.util.concurrent.TimeoutException` stack traces in these 8 games,
thrown from `AiController.chooseSpellAbilitiesToPlayFromList`. This is Forge's own per-decision
AI time limit, not a crash: the AI abandons that decision and carries on, so very busy boards make
it play worse. It is separate from the `-c` match clock and not visible in stdout.

## Statistics design (milestone 4)

Written for anyone consuming the results database.

- **Schema v2** (`PRAGMA user_version = 2`): `runs` (run id, job JSON, Forge version, deck content
  hashes, cards Forge flags as AI-weak), `tasks`, `games`, `seats` (deck file, deck hash, pilot).
  One run folder holds one run; `merge` copies several databases into one. Games record the
  task's seed: a task's games share one `-s` seed and are played in sequence by one Forge process.
- **Winrate** is wins / games that had a winner, with a 95% Wilson interval. Timeouts are reported
  next to it (not as losses) and crashes are excluded entirely. If timeouts correlate with a deck
  (slow, busy boards) the winrate is conditional on the game finishing; check the timeout column.
- **A/B comparison:** Newcombe hybrid-score interval for the difference and a pooled two-sided
  z-test. The "smallest detectable difference" assumes a 25% baseline, 5% significance and 80%
  power: about 5.4 points at 1000 decided games per deck, 4.9 at 1200.
- **Field check:** `compare` warns if the two decks' opponent mixes or seat distributions differ
  by more than 5% total variation, and if they met each other (then results are not independent).
  An `ab` job guarantees identical opponents, seats and seed for both variants by construction.
- **Seat balance:** each task is one rotation of a base seating and all 4 rotations are played
  before the next base seating, so every deck sits in every seat equally often. Base seatings are
  reshuffled each cycle so neighbours vary. A `league` cycles through all `C(n,4)` pods.
- **Ratings:** Plackett-Luce on winners only (P(deck wins pod) = strength / sum of pod strengths),
  fitted with the MM algorithm and a prior of half a win and half a loss against a reference deck
  of strength 1. "Expected winrate vs 3 reference decks" is `s / (s + 3)`. Intervals are percentile
  bootstraps over pod/winner counts (200 resamples take about 5 s). Forge gives no elimination
  order in quiet mode, so a rank-based model (TrueSkill, OpenSkill) would have nothing to use.
  Needs numpy.
- A tiny real A/B (16 games on the starter decks, 2 workers, about 8 minutes) exercised the whole
  path. Seat winrates in it were 25 / 19 / 31 / 25% for seats 1-4 over 16 games each: far too few
  games to say anything about seat advantage.

## Why games are slow (profiled in milestone 4)

One slow smoke-run game was replayed with its seed (853 s versus 913 s the first time, same winner,
27 turns as printed by Forge, 53 real turns, about 14 rounds): slowness is a property of the game, not of the machine. Findings:

- A game runs on **one thread** (about 1 core). GC is not the cause: pauses total 2 s in 636 s (the
  GC log uses decimal commas, so `1,630ms` is 1.6 ms).
- In the last third of the game, 98% of 87 thread-dump samples were in the AI's priority loop:
  `AiController.chooseSpellAbilityToPlay` -> `ComputerUtilAbility.getSpellAbilities` ->
  `GameActionUtil.getAlternativeCosts` -> `GameAction.checkStaticAbilities`. For every candidate
  action the AI asks for, Forge recomputes the continuous effects of the whole board
  (`StaticAbilityContinuous`, `CardProperty.cardHasProperty` was the top frame in 71% of samples).
  Cost therefore grows with board size times number of candidate actions, and every player's
  priority passes pay it.
- Earlier in the game Forge printed its own "AI eval thread at timeout" stack: the AI was inside
  nested combat prediction (`predictNextCombatsRemainingLife` -> `AiAttackController` ->
  `AiBlockController.makeChumpBlocks`, recursive), triggered by deciding whether to cast a pump
  spell. That is the per-decision AI time limit that produces the `TimeoutException` traces.
- Forge sim prints the game log only when the game ends, so progress cannot be watched live.
- Forge has a `MATCH_AI_TIMEOUT` preference (name seen in the jar; default and file key not yet
  checked) that bounds time per AI decision. Lowering it might speed games up at the price of
  weaker play; not tried.
- Only one game was profiled in depth; "big boards of tokens cause it" is the likely but unproven
  explanation of the 45x spread between games.

### Speed-up attempts

- **Known upstream problem:** Forge issue #6149 ("Permanent blanket effects massively slow down AI
  response time", open since 2024) describes this: cards with board-wide continuous effects (Urborg,
  Yavimaya, Painter's Servant, Mycosynth Lattice, Teferi...) make the AI extremely slow. No commit
  since 2.0.16 (checked 2026-11-24) touches the hot path (`GameActionUtil.getAlternativeCosts`,
  which recomputes all static abilities when any static ability affects spells on the stack).
  Which card slowed the profiled game is unknown: a crude script search of the 11 playgroup decks
  found no known offender.
- **JVM flags** (same seeded 81-second game, 4 JVMs at once, same winner every time): default G1
  107 s, `-XX:+UseParallelGC -Xmn700m` 104 s, `-XX:+UseSerialGC -Xmn700m` 112 s,
  `-XX:-TieredCompilation` 95 s. Differences are within noise except possibly `-XX:-TieredCompilation`
  (about 12% faster); not adopted. GC is not the bottleneck.
- Per-game speed cannot be improved without changing Forge; throughput scales with worker count.

## Report (milestone 5)

`report/` builds one self-contained HTML page: `build.py` gathers plain data from the stats
modules, `svg.py` draws the charts as inline SVG (interval dot plots and histograms, styled by
CSS classes so they follow light/dark mode), `render.py` fills `templates/report.html.j2`
with Jinja2. Autoescaping is switched on explicitly because Jinja's default only covers `.html`
templates and ours is `.j2`; a test with a hostile deck name guards this. The report states the
Forge-AI disclaimer at the top, shows timeouts and crashes separately, and repeats every `compare`
warning in the A/B section.

## Remote runs (milestone 6)

- **Run box:** a shared Linux machine reached over ssh. AMD Ryzen 9 5900X
  with 20 threads visible, 60 GB RAM of which about 22 GB were in use by other people, Ubuntu
  26.04, Docker 29.9 usable without sudo, no Java or uv installed. The disk was 97% full
  (69 GB free); the image is 1.7 GB.
- Everything runs in Docker (`Dockerfile`: Temurin 21 JRE, uv-managed Python under `/opt/python`,
  the package in `/app/.venv`, Forge pinned under `/app/vendor`). The container runs as the
  remote user's uid so result files belong to that user; Forge writes only to the per-worker
  `user.home` under `/work`, so the image itself stays read-only.
- Inside a container, `os.cpu_count()` and psutil see the **host's** CPUs and RAM, not the
  container limits, so the worker count must be capped explicitly (`remote run --workers`, which
  sets `workers.max` in the bundled job).
- Stored jobs exclude the deck folder and worker limits, so a run folder resumes after moving
  between machines.
- A run treats SIGTERM like Ctrl+C. `docker stop` therefore kills the Forge processes, keeps every
  finished game, and exits with code 130; Docker's `on-failure` restart policy does not restart a
  container that was stopped by hand.
- **Recovery, tested locally in Docker** (starter decks, 2 workers): `docker stop` mid-run ->
  exit 130, no Java process left, both finished games kept; `docker start` resumed and finished
  all 8 games with no duplicate tasks. `docker kill -s KILL` -> exit 137 and **no automatic
  restart**: Docker treats `kill` like `stop`, a manual action. Its `on-failure` restart covers
  only the runner failing by itself. Forge processes that die are retried inside the run.
  Someone stopping or killing the container, or a reboot, needs `remote run` again, which resumes
  from the saved games; `remote status` says which case happened. Killing the container's main
  process from the host with `kill -9` is refused (permission denied) even for the same user.
- **Watchdog** (`remote watchdog install`): a cron entry every 10 minutes runs `watchdog.sh`, which
  resumes any job whose container is missing or exited with a non-zero code, unless the job was
  stopped with `remote stop` (marker file `jobs/<job>/stopped`). Tested locally against real
  containers: missing -> started, running -> untouched, stopped by someone else -> resumed,
  stopped with the marker -> untouched.
- Containers run with `--init`: without it Python is PID 1, which ignores SIGTERM until the run
  installs its handler, so a `docker stop` during start-up waited the full grace period and ended
  in SIGKILL (exit 137).
