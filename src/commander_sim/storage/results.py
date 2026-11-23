"""SQLite store for one run: every game, its seats, and which tasks are finished."""

import sqlite3
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from commander_sim.forge.output import GameResult, Outcome
from commander_sim.pilots import Pilot

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    task_index INTEGER PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('done', 'failed')),
    attempts INTEGER NOT NULL,
    error TEXT
);
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    forge_version TEXT NOT NULL,
    task_index INTEGER NOT NULL,
    game_number INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    winner_seat INTEGER,
    turns INTEGER,
    duration_ms INTEGER,
    UNIQUE (task_index, game_number)
);
CREATE TABLE IF NOT EXISTS seats (
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    seat INTEGER NOT NULL,
    deck TEXT NOT NULL,
    pilot TEXT NOT NULL,
    PRIMARY KEY (game_id, seat)
);
"""


class RunMismatchError(RuntimeError):
    """The run folder already holds results for a different job or Forge version."""


@dataclass(frozen=True)
class TaskRecord:
    """The outcome of one task: its games, or crash games plus the error that caused them."""

    task_index: int
    seed: int
    seat_decks: tuple[str, ...]
    games: tuple[GameResult, ...]
    attempts: int
    error: str | None = None
    pilot: Pilot = Pilot.FORGE_AI

    @property
    def failed(self) -> bool:
        return self.error is not None


class ResultStore:
    """Single-writer store. Use from one thread only."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def init_run(self, job_json: str, forge_version: str) -> str:
        """Register this job and Forge version (first call) or verify them (resume).

        Returns the run id.
        """
        expected = {"job": job_json, "forge_version": forge_version}
        stored = dict(self._db.execute("SELECT key, value FROM meta"))
        if not stored:
            run_id = uuid.uuid4().hex
            with self._db:
                self._db.executemany(
                    "INSERT INTO meta VALUES (?, ?)", [("run_id", run_id), *expected.items()]
                )
            return run_id
        if any(stored.get(key) != value for key, value in expected.items()):
            raise RunMismatchError(
                "This run folder was created with a different job or Forge version; "
                "use a new job name or delete the folder."
            )
        return stored["run_id"]

    def completed_tasks(self) -> set[int]:
        rows = self._db.execute("SELECT task_index FROM tasks WHERE status = 'done'")
        return {row[0] for row in rows}

    def save_task(self, record: TaskRecord, run_id: str, forge_version: str) -> None:
        """Atomically replace everything stored for this task (a retried failure included)."""
        with self._db:
            self._db.execute("DELETE FROM games WHERE task_index = ?", (record.task_index,))
            self._db.execute(
                "INSERT OR REPLACE INTO tasks VALUES (?, ?, ?, ?)",
                (
                    record.task_index,
                    "failed" if record.failed else "done",
                    record.attempts,
                    record.error,
                ),
            )
            for game in record.games:
                cursor = self._db.execute(
                    "INSERT INTO games (run_id, forge_version, task_index, game_number, seed,"
                    " outcome, winner_seat, turns, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        forge_version,
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
                    "INSERT INTO seats VALUES (?, ?, ?, ?)",
                    [
                        (cursor.lastrowid, seat, deck, record.pilot.value)
                        for seat, deck in enumerate(record.seat_decks, start=1)
                    ],
                )

    def outcome_counts(self) -> dict[Outcome, int]:
        rows = self._db.execute("SELECT outcome, COUNT(*) FROM games GROUP BY outcome")
        return {Outcome(outcome): count for outcome, count in rows}

    def winner_counts(self) -> dict[str, int]:
        """Wins per deck."""
        rows = self._db.execute(
            "SELECT s.deck, COUNT(*) FROM games g JOIN seats s"
            " ON s.game_id = g.id AND s.seat = g.winner_seat"
            " WHERE g.outcome = ? GROUP BY s.deck",
            (Outcome.WIN.value,),
        )
        return dict(rows)

    def failed_errors(self) -> Sequence[tuple[int, str]]:
        rows = self._db.execute("SELECT task_index, error FROM tasks WHERE status = 'failed'")
        return list(rows)
