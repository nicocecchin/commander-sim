import xml.etree.ElementTree as ET

import pytest

from commander_sim.report.svg import (
    LABEL_WIDTH,
    RIGHT_PAD,
    WIDTH,
    IntervalRow,
    histogram,
    interval_chart,
)

NS = {"svg": "http://www.w3.org/2000/svg"}


def parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def test_interval_chart_is_valid_xml_with_one_dot_per_row():
    rows = [IntervalRow("a", 0.2, 0.3, 0.4), IntervalRow("b", 0.1, 0.15, 0.2)]
    root = parse(interval_chart(rows, "Winrates", baseline=0.25))
    assert len(root.findall(".//svg:circle", NS)) == 2
    assert len(root.findall(".//svg:line[@class='baseline']", NS)) == 1


def test_dot_and_interval_ends_are_placed_proportionally_on_the_axis():
    # Axis runs 0-40% here, so 30% sits three quarters along the plot.
    root = parse(interval_chart([IntervalRow("a", 0.2, 0.3, 0.4)], "t"))
    plot_width = WIDTH - LABEL_WIDTH - RIGHT_PAD
    dot = float(root.find(".//svg:circle", NS).get("cx"))
    assert dot == pytest.approx(LABEL_WIDTH + 0.75 * plot_width, abs=0.1)
    bar = root.findall(".//svg:line[@class='ci']", NS)[0]
    assert float(bar.get("x1")) == pytest.approx(LABEL_WIDTH + 0.5 * plot_width, abs=0.1)
    assert float(bar.get("x2")) == pytest.approx(LABEL_WIDTH + plot_width, abs=0.1)


def test_labels_are_escaped_and_long_labels_shortened():
    svg = interval_chart([IntervalRow("<b>&" + "x" * 60, 0.1, 0.2, 0.3)], "t<>")
    root = parse(svg)
    label = root.find(".//svg:text[@class='label']", NS).text
    assert label.startswith("<b>&") and label.endswith("…")
    assert "<b>" not in svg.replace("&lt;b&gt;", "")


def test_interval_chart_without_rows_is_empty():
    assert interval_chart([], "t") == ""


def test_histogram_bars_are_proportional_to_counts():
    root = parse(histogram([1, 1, 2, 3], "Rounds", "rounds", integers=True))
    heights = [float(r.get("height")) for r in root.findall(".//svg:rect", NS)]
    assert len(heights) == 3
    assert heights[0] == pytest.approx(2 * heights[1])
    assert heights[1] == pytest.approx(heights[2])


def test_histogram_with_identical_values_and_without_values():
    root = parse(histogram([5.0, 5.0], "t", "x"))
    assert len(root.findall(".//svg:rect", NS)) >= 1
    assert histogram([], "t", "x") == ""
