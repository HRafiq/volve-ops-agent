"""Clopper-Pearson and WAPE, checked against values computed independently."""

from __future__ import annotations

import pytest

from volve_ops.domain.stats import clopper_pearson, wape


@pytest.mark.parametrize(
    ("k", "n", "lower", "upper"),
    [
        # Textbook values, to four decimals.
        (0, 10, 0.0000, 0.3085),
        (1, 10, 0.0025, 0.4450),
        (5, 10, 0.1871, 0.8129),
        (10, 10, 0.6915, 1.0000),
    ],
)
def test_matches_published_interval_values(k: int, n: int, lower: float, upper: float) -> None:
    lo, hi = clopper_pearson(k, n)
    assert lo == pytest.approx(lower, abs=5e-4)
    assert hi == pytest.approx(upper, abs=5e-4)


def test_the_interval_narrows_as_evidence_grows() -> None:
    narrow = clopper_pearson(100, 1000)
    wide = clopper_pearson(10, 100)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_containment_is_impossible_at_the_sample_size_the_protocol_rejects() -> None:
    """Why the calibration gate is 150 evaluated days and not 60."""
    assert not any(
        clopper_pearson(k, 60)[0] >= 0.05 and clopper_pearson(k, 60)[1] <= 0.20 for k in range(61)
    )
    assert any(
        clopper_pearson(k, 150)[0] >= 0.05 and clopper_pearson(k, 150)[1] <= 0.20
        for k in range(151)
    )


def test_invalid_counts_are_refused() -> None:
    with pytest.raises(ValueError):
        clopper_pearson(5, 0)
    with pytest.raises(ValueError):
        clopper_pearson(11, 10)


def test_wape_is_the_ratio_of_absolute_error_to_absolute_actual() -> None:
    assert wape([100.0, 100.0], [90.0, 110.0]) == pytest.approx(0.1)
    assert wape([100.0], [100.0]) == 0.0


def test_wape_refuses_rather_than_returning_zero_when_nothing_was_produced() -> None:
    with pytest.raises(ValueError, match="sum to zero"):
        wape([0.0, 0.0], [10.0, 20.0])


def test_wape_requires_matching_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        wape([1.0, 2.0], [1.0])
