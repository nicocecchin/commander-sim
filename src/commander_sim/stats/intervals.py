"""Confidence intervals and tests for proportions. Pure functions."""

import math
from statistics import NormalDist

_NORMAL = NormalDist()
Z95 = _NORMAL.inv_cdf(0.975)
DEFAULT_BASELINE = 0.25  # winrate of an average deck in a 4-player pod


def wilson_interval(successes: int, trials: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion; (0, 1) when there are no trials."""
    if trials == 0:
        return 0.0, 1.0
    p = successes / trials
    denominator = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def difference_interval(
    successes_a: int, trials_a: int, successes_b: int, trials_b: int
) -> tuple[float, float]:
    """Newcombe (hybrid score) interval for p_b - p_a."""
    p_a, p_b = successes_a / trials_a, successes_b / trials_b
    low_a, high_a = wilson_interval(successes_a, trials_a)
    low_b, high_b = wilson_interval(successes_b, trials_b)
    diff = p_b - p_a
    return (
        diff - math.sqrt((p_b - low_b) ** 2 + (high_a - p_a) ** 2),
        diff + math.sqrt((high_b - p_b) ** 2 + (p_a - low_a) ** 2),
    )


def two_proportion_p_value(
    successes_a: int, trials_a: int, successes_b: int, trials_b: int
) -> float:
    """Two-sided p-value of the pooled z-test for equal proportions."""
    pooled = (successes_a + successes_b) / (trials_a + trials_b)
    spread = math.sqrt(pooled * (1 - pooled) * (1 / trials_a + 1 / trials_b))
    if spread == 0:
        return 1.0
    z = (successes_b / trials_b - successes_a / trials_a) / spread
    return 2 * (1 - _NORMAL.cdf(abs(z)))


def min_detectable_difference(
    trials_a: int,
    trials_b: int,
    baseline: float = DEFAULT_BASELINE,
    alpha: float = 0.05,
    power: float = 0.8,
) -> float:
    """Smallest true winrate difference a two-sided test would detect with the given power."""
    z_alpha = _NORMAL.inv_cdf(1 - alpha / 2)
    z_power = _NORMAL.inv_cdf(power)
    return (z_alpha + z_power) * math.sqrt(
        baseline * (1 - baseline) * (1 / trials_a + 1 / trials_b)
    )
