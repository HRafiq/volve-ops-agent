"""Small statistical helpers with no dependency beyond the standard library.

Clopper-Pearson is implemented here rather than pulled in from scipy. The protocol commits to
that specific interval, and computing it by bisection on the binomial tail is a dozen lines,
exact to whatever tolerance is asked, and readable by anyone checking whether the calibration
criterion does what it claims.
"""

from __future__ import annotations

from math import comb


def binomial_tail_at_least(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return sum(comb(n, i) * p**i * (1.0 - p) ** (n - i) for i in range(k, n + 1))


def binomial_tail_at_most(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return sum(comb(n, i) * p**i * (1.0 - p) ** (n - i) for i in range(0, k + 1))


def clopper_pearson(
    k: int, n: int, *, confidence: float = 0.95, tol: float = 1e-9
) -> tuple[float, float]:
    """Exact binomial confidence interval for k successes in n trials.

    Conservative by construction: actual coverage is at least the nominal level. That is the
    right direction for a calibration gate, where passing a well whose rate cannot be pinned
    down would be the worse error.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= k <= n:
        raise ValueError(f"k={k} outside 0..{n}")

    alpha = 1.0 - confidence
    lower, upper = 0.0, 1.0

    if k > 0:
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2.0
            # P(X >= k | p) increases with p; find where it equals alpha/2.
            if binomial_tail_at_least(k, n, mid) < alpha / 2.0:
                lo = mid
            else:
                hi = mid
            if hi - lo < tol:
                break
        lower = (lo + hi) / 2.0

    if k < n:
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2.0
            # P(X <= k | p) decreases with p; find where it equals alpha/2.
            if binomial_tail_at_most(k, n, mid) > alpha / 2.0:
                lo = mid
            else:
                hi = mid
            if hi - lo < tol:
                break
        upper = (lo + hi) / 2.0

    return lower, upper


def wape(actual: list[float], predicted: list[float]) -> float:
    """Weighted absolute percentage error: sum|a - p| / sum|a|.

    Undefined when the actuals sum to zero, which is raised rather than returned as zero: a
    model cannot be perfect on a well that produced nothing.
    """
    if len(actual) != len(predicted):
        raise ValueError("actual and predicted must be the same length")
    denominator = sum(abs(a) for a in actual)
    if denominator == 0.0:
        raise ValueError("cannot compute WAPE when the actuals sum to zero")
    return sum(abs(a - p) for a, p in zip(actual, predicted, strict=True)) / denominator
