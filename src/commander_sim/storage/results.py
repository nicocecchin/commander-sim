"""SQLite store for runs: every game, its seats, and which tasks are finished.

One database normally holds one run (a run folder). `import_runs` merges several databases into
one for analysis.
"""

import json
import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from commander_sim.forge.output import GameResult, Outcome
from commander_sim.pilots import Pilot

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    forge_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    job_json TEXT NOT NULL,
    deck_hashes_json TEXT NOT NULL,
    ai_weak_cards_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    task_index INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('done', 'failed')),
    attempts INTEGER NOT NULL,
    error TEXT,
    PRIMARY KEY (run_id, task_index)
);
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    task_index INTEGER NOT NULL,
    game_number INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    winner_seat INTEGER,
    turns INTEGER,
    duration_ms INTEGER,
    UNIQUE (run_id, task_index, game_number)
);
CREATE TABLE IF NOT EXISTS seats (
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    seat INTEGER NOT NULL,
    deck TEXT NOT NULL,
    deck_hash TEXT NOT NULL,
    pilot TEXT NOT NULL,
    PRIMARY KEY (game_id, seat)
);
"""


class RunMismatchError(RuntimeError):
    """The database already holds a run with a different job, Forge version or deck contents."""


class SchemaVersionError(RuntimeError):
    """The database was written by an incompatible version of this tool."""


@dataclass(frozen=True)
class TaskRecord:
    """The outcome of one task: its games, or crash games plus the error that caused them."""

    task_index: int
    seed: int
    seat_decks: tuple[str, ...]
    seat_hashes: tuple[str, ...]
    games: tuple[GameResult, ...]
    attempts: int
    error: str | None = None
    pilot: Pilot = Pilot.FORGE_AI

    @property
    def failed(self) -> bool:
        return self.error is not None


@dataclass(frozen=True)
class Seat:
    deck: str
    deck_hash: str
    pilot: Pilot


@dataclass(frozen=True)
class GameRecord:
    """One stored game with its seats in seat order (seat 1 first)."""

    run_id: str
    task_index: int
    game_number: int
    outcome: Outcome
    winner_seat: int | None
    turns: int | None
    duration_ms: int | None
    seats: tuple[Seat, ...]

    @property
    def winner(self) -> Seat | None:
        return self.seats[self.winner_seat - 1] if self.winner_seat else None


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    name: str
    forge_version: str
    deck_hashes: Mapping[str, str]
    ai_weak_cards: Mapping[str, Sequence[str]]


class ResultStore:
    """Single-writer store. Use from one thread only."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute("PRAGMA foreign_keys = ON")
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            self._db.close()
            raise SchemaVersionError(
                f"{path} has schema version {version}; this tool uses {SCHEMA_VERSION}"
            )
        self._db.executescript(SCHEMA)
        self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self._db.close()

    def init_run(
        self,
        name: str,
        job_json: str,
        forge_version: str,
        deck_hashes: Mapping[str, str],
        ai_weak_cards: Mapping[str, Sequence[str]],
    ) -> str:
        """Register this run (first call) or verify it is the same run (resume). Returns its id."""
        fingerprint = (name, forge_version, job_json, json.dumps(deck_hashes, sort_keys=True))
        existing = self._db.execute(
            "SELECT run_id, name, forge_version, job_json, deck_hashes_json FROM runs"
        ).fetchall()
        if not existing:
            run_id = uuid.uuid4().hex
            with self._db:
                self._db.execute(
                    "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        name,
                        forge_version,
                        datetime.now(UTC).isoformat(timespec="seconds"),
                        job_json,
                        json.dumps(deck_hashes, sort_keys=True),
                        json.dumps(ai_weak_cards, sort_keys=True),
                    ),
                )
            return run_id
        run_id, *stored = existing[0]
        if tuple(stored) != fingerprint:
            raise RunMismatchError(
                "This run folder was created with a different job, Forge version or deck "
                "contents; use a new job name or delete the folder."
            )
        return run_id

    def completed_tasks(self, run_id: str) -> set[int]:
        rows = self._db.execute(
            "SELECT task_index FROM tasks WHERE run_id = ? AND status = 'done'", (run_id,)
        )
        return {row[0] for row in rows}

    def save_task(self, record: TaskRecord, run_id: str) -> None:
        """Atomically replace everything stored for this task (a retried failure included)."""
        with self._db:
            self._db.execute(
                "DELETE FROM games WHERE run_id = ? AND task_index = ?",
                (run_id, record.task_index),
            )
            self._db.execute(
                "INSERT OR REPLACE INTO tasks VALUES (?, ?, ?, ?, ?)",
                (
                    run_id,
                    record.task_index,
                    "failed" if record.failed else "done",
                    record.attempts,
                    record.error,
                ),
            )
            for game in record.games:
                cursor = self._db.execute(
                    "INSERT INTO games (run_id, task_index, game_number, seed, outcome,"
                    " winner_seat, turns, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        record.task_index,
                        game.number,
                        record.seed,
                        game.outcome.value,
                        game.winner_seat,
                        game.turns,
                        game.duration_ms,
                    ),
                )
                self._db.executemany(
                    "INSERT INTO seats VALUES (?, ?, ?, ?, ?)",
                    [
                        (cursor.lastrowid, seat, deck, deck_hash, record.pilot.value)
                        for seat, (deck, deck_hash) in enumerate(
                            zip(record.seat_decks, record.seat_hashes, strict=True), start=1
                        )
                    ],
                )

    def outcome_counts(self, run_id: str | None = None) -> dict[Outcome, int]:
        rows = self._db.execute(
            "SELECT outcome, COUNT(*) FROM games"
            " WHERE :run_id IS NULL OR run_id = :run_id GROUP BY outcome",
            {"run_id": run_id},
        )
        return {Outcome(outcome): count for outcome, count in rows}

    def failed_errors(self, run_id: str) -> list[tuple[int, str]]:
        rows = self._db.execute(
            "SELECT task_index, error FROM tasks WHERE run_id = ? AND status = 'failed'",
            (run_id,),
        )
        return list(rows)

    def read_runs(self) -> list[RunInfo]:
        rows = self._db.execute(
            "SELECT run_id, name, forge_version, deck_hashes_json, ai_weak_cards_json FROM runs"
            " ORDER BY created_at"
        )
        return [
            RunInfo(run_id, name, forge, json.loads(hashes), json.loads(weak))
            for run_id, name, forge, hashes, weak in rows
        ]

    def read_games(self) -> list[GameRecord]:
        seats: dict[int, list[Seat]] = {}
        for game_id, deck, deck_hash, pilot in self._db.execute(
            "SELECT game_id, deck, deck_hash, pilot FROM seats ORDER BY game_id, seat"
        ):
            seats.setdefault(game_id, []).append(Seat(deck, deck_hash, Pilot(pilot)))
        rows = self._db.execute(
            "SELECT id, run_id, task_index, game_number, outcome, winner_seat, turns, duration_ms"
            " FROM games ORDER BY id"
        )
        return [
            GameRecord(run_id, task, number, Outcome(outcome), winner, turns, ms, tuple(seats[gid]))
            for gid, run_id, task, number, outcome, winner, turns, ms in rows
        ]

    def import_runs(self, other: "ResultStore") -> list[str]:
        """Copy every run of `other` into this store. Returns the imported run ids.

        Raises RunMismatchError, importing nothing, if any run id is already present.
        """
        known = {row[0] for row in self._db.execute("SELECT run_id FROM runs")}
        incoming = [row[0] for row in other._db.execute("SELECT run_id FROM runs")]
        if duplicates := known.intersection(incoming):
            raise RunMismatchError(f"Run(s) already present: {', '.join(sorted(duplicates))}")
        with self._db:
            for table in ("runs", "tasks"):
                for row in other._db.execute(f"SELECT * FROM {table}").fetchall():
                    marks = ", ".join("?" * len(row))
                    self._db.execute(f"INSERT INTO {table} VALUES ({marks})", row)
            for old_id, *game in other._db.execute(
                "SELECT id, run_id, task_index, game_number, seed, outcome, winner_seat, turns,"
                " duration_ms FROM games ORDER BY id"
            ).fetchall():
                new_id = self._db.execute(
                    "INSERT INTO games (run_id, task_index, game_number, seed, outcome,"
                    " winner_seat, turns, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    game,
                ).lastrowid
                self._db.executemany(
                    "INSERT INTO seats VALUES (?, ?, ?, ?, ?)",
                    [
                        (new_id, *seat)
                        for seat in other._db.execute(
                            "SELECT seat, deck, deck_hash, pilot FROM seats WHERE game_id = ?",
                            (old_id,),
                        )
                    ],
                )
        return incoming
