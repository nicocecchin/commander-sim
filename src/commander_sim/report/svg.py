"""Small inline-SVG charts for the report. Colours come from CSS classes the page defines."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

WIDTH = 720
LABEL_WIDTH = 230
RIGHT_PAD = 24
ROW_HEIGHT = 30
AXIS_HEIGHT = 30
MAX_LABEL_CHARS = 34
HIST_HEIGHT = 220
HIST_LEFT = 44
HIST_BOTTOM = 40
HIST_TOP = 14
MAX_INTEGER_BINS = 40


@dataclass(frozen=True)
class IntervalRow:
    label: str
    low: float
    point: float
    high: float


def _shorten(text: str) -> str:
    return text if len(text) <= MAX_LABEL_CHARS else text[: MAX_LABEL_CHARS - 1] + "…"


def _axis_max(rows: Sequence[IntervalRow], baseline: float | None) -> float:
    top = max([row.high for row in rows] + ([baseline] if baseline else []) + [0.1])
    return min(1.0, math.ceil(round(top * 10, 9)) / 10)


def _percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def interval_chart(rows: Sequence[IntervalRow], title: str, baseline: float | None = None) -> str:
    """A dot per row with its interval as a bar, on a 0-100% axis.

    `baseline` draws a dashed reference line, e.g. the 25% an average deck wins in a pod of 4.
    """
    if not rows:
        return ""
    axis_max = _axis_max(rows, baseline)
    plot_width = WIDTH - LABEL_WIDTH - RIGHT_PAD
    height = AXIS_HEIGHT + ROW_HEIGHT * len(rows) + 8

    def x(value: float) -> float:
        return LABEL_WIDTH + value / axis_max * plot_width

    step = 0.1 if axis_max <= 0.5 else 0.2
    parts = [
        f'<svg viewBox="0 0 {WIDTH} {height}" role="img" aria-label={quoteattr(title)} '
        'class="chart" xmlns="http://www.w3.org/2000/svg">',
        f"<title>{escape(title)}</title>",
    ]
    tick = 0.0
    while tick <= axis_max + 1e-9:
        parts.append(
            f'<line class="grid" x1="{x(tick):.1f}" x2="{x(tick):.1f}" '
            f'y1="{AXIS_HEIGHT - 6}" y2="{height - 4}"/>'
            f'<text class="axis" x="{x(tick):.1f}" y="{AXIS_HEIGHT - 12}" '
            f'text-anchor="middle">{_percent(tick)}</text>'
        )
        tick += step
    if baseline is not None:
        parts.append(
            f'<line class="baseline" x1="{x(baseline):.1f}" x2="{x(baseline):.1f}" '
            f'y1="{AXIS_HEIGHT - 6}" y2="{height - 4}"/>'
        )
    for index, row in enumerate(rows):
        y = AXIS_HEIGHT + ROW_HEIGHT * index + ROW_HEIGHT / 2
        tooltip = (
            f"{row.label}: {row.point * 100:.1f}% "
            f"(95% CI {row.low * 100:.1f}% to {row.high * 100:.1f}%)"
        )
        parts.append(
            f"<g><title>{escape(tooltip)}</title>"
            f'<text class="label" x="{LABEL_WIDTH - 10}" y="{y + 4:.1f}" text-anchor="end">'
            f"{escape(_shorten(row.label))}</text>"
            f'<line class="ci" x1="{x(row.low):.1f}" x2="{x(row.high):.1f}" '
            f'y1="{y:.1f}" y2="{y:.1f}"/>'
            f'<line class="ci" x1="{x(row.low):.1f}" x2="{x(row.low):.1f}" '
            f'y1="{y - 5:.1f}" y2="{y + 5:.1f}"/>'
            f'<line class="ci" x1="{x(row.high):.1f}" x2="{x(row.high):.1f}" '
            f'y1="{y - 5:.1f}" y2="{y + 5:.1f}"/>'
            f'<circle class="dot" cx="{x(row.point):.1f}" cy="{y:.1f}" r="5"/></g>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _histogram_bins(values: Sequence[float], integers: bool) -> tuple[float, float, int]:
    low, high = min(values), max(values)
    if integers and high - low < MAX_INTEGER_BINS:
        return low - 0.5, high + 0.5, int(high - low) + 1
    count = max(1, min(20, math.ceil(math.sqrt(len(values)))))
    return low, high if high > low else low + 1, count


def histogram(values: Sequence[float], title: str, x_label: str, integers: bool = False) -> str:
    """Bar histogram of `values`; `integers` gives one bar per whole number for small ranges."""
    if not values:
        return ""
    start, end, count = _histogram_bins(values, integers)
    width = (end - start) / count
    precision = 0 if integers or end - start >= 10 else 1
    counts = [0] * count
    for value in values:
        counts[min(count - 1, int((value - start) / width))] += 1
    top = max(counts)
    plot_width = WIDTH - HIST_LEFT - RIGHT_PAD
    plot_height = HIST_HEIGHT - HIST_BOTTOM - HIST_TOP
    bar_width = plot_width / count

    parts = [
        f'<svg viewBox="0 0 {WIDTH} {HIST_HEIGHT}" role="img" aria-label={quoteattr(title)} '
        'class="chart" xmlns="http://www.w3.org/2000/svg">',
        f"<title>{escape(title)}</title>",
        f'<line class="grid" x1="{HIST_LEFT}" x2="{WIDTH - RIGHT_PAD}" '
        f'y1="{HIST_TOP + plot_height}" y2="{HIST_TOP + plot_height}"/>',
        f'<text class="axis" x="{HIST_LEFT - 8}" y="{HIST_TOP + 10}" '
        f'text-anchor="end">{top}</text>',
        f'<text class="axis" x="{HIST_LEFT - 8}" y="{HIST_TOP + plot_height}" '
        'text-anchor="end">0</text>',
    ]
    for index, n in enumerate(counts):
        bar_height = plot_height * n / top
        low_edge = start + index * width
        parts.append(
            f"<g><title>{low_edge:.{precision}f} to {low_edge + width:.{precision}f}: "
            f"{n} game(s)</title>"
            f'<rect class="bar" x="{HIST_LEFT + index * bar_width + 1:.1f}" '
            f'y="{HIST_TOP + plot_height - bar_height:.1f}" '
            f'width="{max(bar_width - 2, 1):.1f}" height="{bar_height:.1f}"/></g>'
        )
    half = 0.5 if integers else 0
    labels = {
        HIST_LEFT: f"{start + half:.{precision}f}",
        HIST_LEFT + plot_width: f"{end - half:.{precision}f}",
    }
    for position, text in labels.items():
        parts.append(
            f'<text class="axis" x="{position}" y="{HIST_TOP + plot_height + 16}" '
            f'text-anchor="middle">{text}</text>'
        )
    parts.append(
        f'<text class="axis" x="{HIST_LEFT + plot_width / 2}" '
        f'y="{HIST_HEIGHT - 6}" text-anchor="middle">{escape(x_label)}</text></svg>'
    )
    return "".join(parts)
