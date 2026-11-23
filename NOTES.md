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
  result block is printed. Both start with ~20 lines of noise ("The card ... was not assigned to
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
- Turn count is the global turn counter (all players), so a 4-player game of 34 turns is about
  8 rounds.
- **Timeout trap:** when `-c` expires Forge prints `Stopping slow match as draw`, then declares
  **every** player "has won" and names an arbitrary seat in `Game Result`. A timeout must be
  detected from the `Stopping slow match` line, never from the winner lines. The parser does this
  (`forge/output.py`).
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

- Behaviour on a Forge crash / OOM / hung JVM (milestone 2).
- Windows/macOS user-dir isolation (see above).
- Whether a genuine draw can occur besides timeouts.
