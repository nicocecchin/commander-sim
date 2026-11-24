"""Turn report data into a self-contained HTML page."""

from datetime import datetime
from pathlib import Path
from statistics import mean

from jinja2 import Environment, PackageLoader
from markupsafe import Markup

from commander_sim.forge.output import Outcome
from commander_sim.report.build import AbSection, ReportData, build_report_data
from commander_sim.report.svg import IntervalRow, histogram, interval_chart
from commander_sim.stats.format import DISCLAIMER, deck_label, interval_text, percent
from commander_sim.storage.load import LoadedResults

_DEFAULT_SEAT_COUNT = 4

_environment = Environment(
    loader=PackageLoader("commander_sim.report", "templates"),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)
_environment.filters["pct"] = percent
_environment.filters["ci"] = interval_text


def _chart(svg: str) -> Markup:
    """Wrap a chart so that on narrow screens it scrolls instead of shrinking its text."""
    return Markup(f'<div class="scroll">{svg}</div>') if svg else Markup("")


def _title(data: ReportData) -> str:
    names = [run.info.name for run in data.runs]
    return f"Commander sim: {', '.join(names) if len(names) <= 3 else f'{len(names)} runs'}"


def _ab_context(section: AbSection, baseline: float) -> dict[str, object]:
    c = section.comparison
    low, high = c.interval
    rows = [IntervalRow(s.deck, s.interval[0], s.winrate, s.interval[1]) for s in (c.a, c.b)]
    return {
        "a": section.variants[0],
        "b": section.variants[1],
        "run_names": section.run_names,
        "difference": f"{c.difference * 100:+.1f} points",
        "interval": f"{low * 100:+.1f} to {high * 100:+.1f}",
        "p_value": f"{c.p_value:.3f}",
        "detectable": f"{c.min_detectable * 100:.1f} points",
        "chart": _chart(interval_chart(rows, "A/B winrates", baseline)),
        "warnings": c.warnings,
    }


def render_report(data: ReportData) -> str:
    seat_count = data.seat_balance.seat_count or _DEFAULT_SEAT_COUNT
    baseline = 1 / seat_count
    owners = data.owners

    def label(deck: str) -> str:
        return deck_label(deck, owners)

    deck_rows = [
        IntervalRow(label(s.deck), s.interval[0], s.winrate, s.interval[1]) for s in data.decks
    ]
    rating_rows = [
        IntervalRow(label(r.deck), r.interval[0], r.expected_winrate, r.interval[1])
        for r in data.ratings
    ]
    seat_rows = [
        IntervalRow(f"Seat {s.seat}", s.interval[0], s.winrate, s.interval[1]) for s in data.seats
    ]
    balance = data.seat_balance.counts
    forge_versions = sorted({run.info.forge_version for run in data.runs})
    template = _environment.get_template("report.html.j2")
    return template.render(
        title=_title(data),
        total=data.total_games,
        forge_versions=", ".join(forge_versions),
        generated_at=data.generated_at,
        disclaimer=DISCLAIMER,
        baseline_text=percent(baseline),
        seat_count=seat_count,
        outcomes={o.value: data.outcome_counts.get(o, 0) for o in Outcome},
        speed=data.speed,
        decks=data.decks,
        label=label,
        deck_chart=_chart(interval_chart(deck_rows, "Winrate per deck", baseline)),
        ab_sections=[_ab_context(section, baseline) for section in data.ab_sections],
        rating_chart=_chart(interval_chart(rating_rows, "Expected winrate per deck", baseline)),
        seats=data.seats,
        seat_chart=_chart(interval_chart(seat_rows, "Winrate per seat", baseline)),
        rounds_chart=_chart(histogram(data.rounds, "Rounds per won game", "rounds", integers=True)),
        mean_rounds=mean(data.rounds) if data.rounds else 0.0,
        mean_turns=mean(data.turns) if data.turns else 0.0,
        minutes_chart=_chart(histogram(data.game_minutes, "Minutes per game", "minutes")),
        failures=data.failures,
        deck_versions=data.deck_versions,
        balance=balance,
        balance_max=max((n for counts in balance.values() for n in counts), default=0),
        ai_weak_notes=data.ai_weak_notes,
        runs=data.runs,
    )


def write_report(
    results: LoadedResults, owners: dict[str, str], out: Path, bootstrap: int = 200
) -> Path:
    """Build and write the report for `results`; returns `out`."""
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    html = render_report(build_report_data(results, owners, generated_at, bootstrap))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
