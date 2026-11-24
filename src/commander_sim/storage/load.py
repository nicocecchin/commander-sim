"""Read results from several database files at once."""

from dataclasses import dataclass
from pathlib import Path

from commander_sim.storage.results import GameRecord, ResultStore, RunInfo, TaskFailure


class DatabaseError(ValueError):
    """A results database is missing or overlaps another one."""


@dataclass(frozen=True)
class LoadedResults:
    runs: list[RunInfo]
    games: list[GameRecord]
    failures: list[TaskFailure]


def load_databases(paths: list[Path]) -> LoadedResults:
    """Read every run, game and failed task. The same run in two files is an error."""
    runs: list[RunInfo] = []
    games: list[GameRecord] = []
    failures: list[TaskFailure] = []
    for path in paths:
        if not path.is_file():
            raise DatabaseError(f"{path} does not exist")
        store = ResultStore(path)
        try:
            runs += store.read_runs()
            games += store.read_games()
            failures += store.read_failures()
        finally:
            store.close()
    ids = [run.run_id for run in runs]
    if len(ids) != len(set(ids)):
        raise DatabaseError("The same run appears in more than one database")
    return LoadedResults(runs, games, failures)
