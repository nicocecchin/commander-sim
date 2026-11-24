"""Collect everything the HTML report shows into one plain data object. No formatting here."""

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median

from commander_sim.config import ABMatchup, JobSpec, job_from_portable_json
from commander_sim.forge.output import Outcome
from commander_sim.stats.compare import Comparison, compare_decks
from commander_sim.stats.format import ai_weakness_notes
from commander_sim.stats.ratings import Rating, fit_ratings
from commander_sim.stats.winrates import (
    DeckStats,
    SeatStats,
    deck_stats,
    deck_versions,
    seat_stats,
)
from commander_sim.storage.load import LoadedResults
from commander_sim.storage.results import GameRecord, RunInfo, TaskFailure

_MS_PER_MINUTE = 60_000
_MINUTES_PER_HOUR = 60


@dataclass(frozen=True)
class RunSummary:
    info: RunInfo
    kind: str  # "pod", "ab", "league", or "unknown" if the stored job cannot be read
    games: int


@dataclass(frozen=True)
class AbSection:
    variants: tuple[str, str]
    run_names: tuple[str, ...]
    comparison: Comparison


@dataclass(frozen=True)
class Speed:
    """Game time only: JVM start-up is not included in the worker hours."""

    mean_minutes: float
    median_minutes: float
    longest_minutes: float
    worker_hours: float
    games_per_worker_hour: float


@dataclass(frozen=True)
class SeatBalance:
    decks: tuple[str, ...]
    seat_count: int
    counts: dict[str, tuple[int, ...]]  # deck -> appearances per seat, seat 1 first


@dataclass(frozen=True)
class ReportData:
    generated_at: str
    runs: list[RunSummary]
    outcome_counts: dict[Outcome, int]
    decks: list[DeckStats]
    ratings: list[Rating]
    seats: list[SeatStats]
    ab_sections: list[AbSection]
    rounds: list[int]
    turns: list[int]
    speed: Speed | None
    game_minutes: list[float]
    failures: list[TaskFailure]
    deck_versions: dict[str, set[str]]
    ai_weak_notes: list[str]
    seat_balance: SeatBalance
    owners: dict[str, str]

    @property
    def total_games(self) -> int:
        return sum(self.outcome_counts.values())


def _parse_job(run: RunInfo) -> JobSpec | None:
    try:
        return job_from_portable_json(run.job_json)
    except ValueError:
        return None


def _game_minutes(games: list[GameRecord]) -> list[float]:
    return [
        g.duration_ms / _MS_PER_MINUTE
        for g in games
        if g.outcome is not Outcome.CRASH and g.duration_ms is not None
    ]


def _speed(minutes: list[float]) -> Speed | None:
    if not minutes:
        return None
    worker_hours = sum(minutes) / _MINUTES_PER_HOUR
    return Speed(
        mean_minutes=mean(minutes),
        median_minutes=median(minutes),
        longest_minutes=max(minutes),
        worker_hours=worker_hours,
        games_per_worker_hour=len(minutes) / worker_hours if worker_hours else 0.0,
    )


def _seat_balance(games: list[GameRecord]) -> SeatBalance:
    played = [g for g in games if g.outcome is not Outcome.CRASH]
    seat_count = max((len(g.seats) for g in played), default=0)
    counts: dict[str, list[int]] = defaultdict(lambda: [0] * seat_count)
    for game in played:
        for seat_number, seat in enumerate(game.seats):
            counts[seat.deck][seat_number] += 1
    decks = tuple(sorted(counts))
    return SeatBalance(decks, seat_count, {deck: tuple(counts[deck]) for deck in decks})


def _ab_sections(
    runs: list[RunSummary], games: list[GameRecord], jobs: dict[str, JobSpec]
) -> list[AbSection]:
    runs_by_pair: dict[tuple[str, str], list[RunSummary]] = defaultdict(list)
    for run in runs:
        job = jobs.get(run.info.run_id)
        if job is not None and isinstance(job.matchup, ABMatchup):
            runs_by_pair[job.matchup.variants].append(run)
    sections = []
    for pair, pair_runs in runs_by_pair.items():
        ids = {run.info.run_id for run in pair_runs}
        try:
            comparison = compare_decks([g for g in games if g.run_id in ids], *pair)
        except ValueError:
            continue
        sections.append(AbSection(pair, tuple(run.info.name for run in pair_runs), comparison))
    return sections


def build_report_data(
    results: LoadedResults, owners: dict[str, str], generated_at: str, bootstrap: int = 200
) -> ReportData:
    games = results.games
    jobs = {run.run_id: job for run in results.runs if (job := _parse_job(run))}
    games_per_run: dict[str, int] = defaultdict(int)
    for game in games:
        games_per_run[game.run_id] += 1
    runs = [
        RunSummary(
            run,
            jobs[run.run_id].matchup.kind if run.run_id in jobs else "unknown",
            games_per_run[run.run_id],
        )
        for run in results.runs
    ]
    outcomes: dict[Outcome, int] = defaultdict(int)
    for game in games:
        outcomes[game.outcome] += 1
    wins = [g for g in games if g.outcome is Outcome.WIN]
    minutes = _game_minutes(games)
    return ReportData(
        generated_at=generated_at,
        runs=runs,
        outcome_counts=dict(outcomes),
        decks=deck_stats(games),
        ratings=fit_ratings(games, bootstrap=bootstrap),
        seats=seat_stats(games),
        ab_sections=_ab_sections(runs, games, jobs),
        rounds=[g.rounds for g in wins if g.rounds is not None],
        turns=[g.turns for g in wins if g.turns is not None],
        speed=_speed(minutes),
        game_minutes=minutes,
        failures=results.failures,
        deck_versions=deck_versions(games),
        ai_weak_notes=ai_weakness_notes(results.runs, owners),
        seat_balance=_seat_balance(games),
        owners=owners,
    )
