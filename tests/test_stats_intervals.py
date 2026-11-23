import pytest

from commander_sim.stats.intervals import (
    difference_interval,
    min_detectable_difference,
    two_proportion_p_value,
    wilson_interval,
)


def test_wilson_matches_reference_values():
    low, high = wilson_interval(20, 100)
    assert low == pytest.approx(0.1334, abs=5e-4)
    assert high == pytest.approx(0.2890, abs=5e-4)
    assert wilson_interval(0, 10) == pytest.approx((0.0, 0.2775), abs=5e-4)


def test_wilson_with_no_trials_is_uninformative():
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_newcombe_difference_matches_published_example():
    # Newcombe (1998), method 10: 56/70 versus 48/80 gives 0.2000 (0.0524 to 0.3339).
    low, high = difference_interval(48, 80, 56, 70)
    assert low == pytest.approx(0.0524, abs=1e-3)
    assert high == pytest.approx(0.3339, abs=1e-3)


def test_p_value_of_the_same_example():
    assert two_proportion_p_value(48, 80, 56, 70) == pytest.approx(0.008, abs=1e-3)
    assert two_proportion_p_value(10, 100, 10, 100) == pytest.approx(1.0)


def test_min_detectable_difference_for_a_thousand_games():
    assert min_detectable_difference(1000, 1000) == pytest.approx(0.0543, abs=5e-4)
    assert min_detectable_difference(100, 100) > min_detectable_difference(1000, 1000)
