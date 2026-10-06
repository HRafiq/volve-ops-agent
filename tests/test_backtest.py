"""The section 8 pass marks. These decide which expectation ships, so they are worth pinning."""

from __future__ import annotations

import datetime as dt
import math

import pytest
from pydantic import ValidationError

from volve_ops.domain.backtest import (
    BIAS_MIN_DAYS,
    CALIBRATION_MIN_DAYS,
    HORIZONS,
    EvaluatedDay,
    ModelResult,
    condition_1_relative_wape,
    condition_2_lower_tail,
    condition_3_bias,
)
from volve_ops.domain.day_class import ClassifiedDay, DayClass
from volve_ops.domain.expectation import (
    ExponentialDecline,
    HyperbolicDecline,
    NaiveMedian28,
    NaivePersistence,
)
from volve_ops.ingest.production import ProductionDay, WellStatus


def days(
    *,
    well: str = "W1",
    horizon: int = 7,
    count: int,
    actual: float,
    predicted: float,
    lower: float = 0.0,
    window_index: int = 0,
    first_step: int = 1,
) -> list[EvaluatedDay]:
    return [
        EvaluatedDay(
            well=well,
            horizon=horizon,
            steps_ahead=first_step + i,
            window_index=window_index,
            actual=actual,
            predicted=predicted,
            lower=lower,
            upper=predicted * 2,
        )
        for i in range(count)
    ]


def result(name: str, rows: list[EvaluatedDay]) -> ModelResult:
    return ModelResult(model_name=name, evaluated=tuple(rows))


def across_horizons(**kw: object) -> list[EvaluatedDay]:
    out: list[EvaluatedDay] = []
    for h in HORIZONS:
        out.extend(days(horizon=h, **kw))  # type: ignore[arg-type]
    return out


class TestCondition1:
    def test_a_candidate_must_beat_the_better_baseline_by_the_margin(self) -> None:
        candidate = result("cand", across_horizons(count=20, actual=100.0, predicted=100.0))
        weak = result("weak", across_horizons(count=20, actual=100.0, predicted=50.0))
        outcome = condition_1_relative_wape(candidate, [weak])
        assert outcome.passed

    def test_a_candidate_that_only_ties_fails(self) -> None:
        candidate = result("cand", across_horizons(count=20, actual=100.0, predicted=90.0))
        rival = result("rival", across_horizons(count=20, actual=100.0, predicted=90.0))
        assert not condition_1_relative_wape(candidate, [rival]).passed

    def test_failing_a_single_horizon_fails_the_condition(self) -> None:
        """All three horizons are required; the longest is where carried-forward models die."""
        rows = days(horizon=7, count=20, actual=100.0, predicted=100.0)
        rows += days(horizon=14, count=20, actual=100.0, predicted=100.0)
        rows += days(horizon=28, count=20, actual=100.0, predicted=40.0)
        candidate = result("cand", rows)
        rival = result("rival", across_horizons(count=20, actual=100.0, predicted=85.0))
        assert not condition_1_relative_wape(candidate, [rival]).passed

    def test_the_better_of_several_baselines_is_the_one_to_beat(self) -> None:
        candidate = result("cand", across_horizons(count=20, actual=100.0, predicted=95.0))
        poor = result("poor", across_horizons(count=20, actual=100.0, predicted=50.0))
        good = result("good", across_horizons(count=20, actual=100.0, predicted=97.0))
        assert not condition_1_relative_wape(candidate, [poor, good]).passed


class TestCondition2:
    def test_a_well_inside_the_band_with_enough_days_passes(self) -> None:
        rows: list[EvaluatedDay] = []
        for h in HORIZONS:
            n = CALIBRATION_MIN_DAYS * 2
            below = int(n * 0.10)
            rows += days(horizon=h, count=below, actual=1.0, predicted=10.0, lower=5.0)
            rows += days(horizon=h, count=n - below, actual=10.0, predicted=10.0, lower=5.0)
        assert condition_2_lower_tail(result("m", rows), producer_count=1).passed

    def test_a_well_far_outside_the_band_fails(self) -> None:
        rows: list[EvaluatedDay] = []
        for h in HORIZONS:
            rows += days(
                horizon=h, count=CALIBRATION_MIN_DAYS, actual=1.0, predicted=10.0, lower=5.0
            )
        assert not condition_2_lower_tail(result("m", rows), producer_count=1).passed

    def test_the_pooled_fallback_fires_when_too_few_producers_qualify(self) -> None:
        """Section 8 pools rather than declaring the condition unevaluable."""
        rows: list[EvaluatedDay] = []
        for h in HORIZONS:
            rows += days(
                horizon=h,
                count=CALIBRATION_MIN_DAYS,
                actual=1.0,
                predicted=10.0,
                lower=5.0,
                well="W1",
            )
        outcome = condition_2_lower_tail(result("m", rows), producer_count=6)
        assert "POOLED" in outcome.detail
        assert outcome.evaluable

    def test_the_denominator_is_the_field_not_the_wells_that_happen_to_qualify(self) -> None:
        rows: list[EvaluatedDay] = []
        for h in HORIZONS:
            rows += days(
                horizon=h,
                count=CALIBRATION_MIN_DAYS,
                actual=1.0,
                predicted=10.0,
                lower=5.0,
                well="W1",
            )
        with_field = condition_2_lower_tail(result("m", rows), producer_count=6)
        without = condition_2_lower_tail(result("m", rows), producer_count=1)
        assert "POOLED" in with_field.detail
        assert "POOLED" not in without.detail


class TestCondition3:
    def test_an_unbiased_model_passes(self) -> None:
        rows: list[EvaluatedDay] = []
        for h in HORIZONS:
            rows += days(horizon=h, count=BIAS_MIN_DAYS * 2, actual=100.0, predicted=100.0)
        assert condition_3_bias(result("m", rows)).passed

    def test_a_systematically_biased_model_fails(self) -> None:
        rows: list[EvaluatedDay] = []
        for h in HORIZONS:
            rows += days(horizon=h, count=BIAS_MIN_DAYS * 2, actual=100.0, predicted=120.0)
        assert not condition_3_bias(result("m", rows)).passed

    def test_drift_inside_a_window_fails_even_when_the_mean_is_centred(self) -> None:
        """The half that fails is invisible to a mean over the whole window."""
        rows: list[EvaluatedDay] = []
        for h in HORIZONS:
            half = BIAS_MIN_DAYS
            rows += days(
                horizon=h,
                count=half,
                actual=80.0,
                predicted=100.0,
                window_index=0,
                first_step=1,
            )
            rows += days(
                horizon=h,
                count=half,
                actual=120.0,
                predicted=100.0,
                window_index=0,
                first_step=half + 1,
            )
        outcome = condition_3_bias(result("m", rows))
        assert not outcome.passed
        assert "drift" in outcome.detail

    def test_a_well_below_the_minimum_day_count_is_report_only(self) -> None:
        rows = days(horizon=7, count=BIAS_MIN_DAYS - 1, actual=100.0, predicted=200.0)
        assert not condition_3_bias(result("m", rows)).evaluable


def test_pooled_wape_is_none_without_evaluated_days() -> None:
    assert result("m", []).pooled_wape(7) is None


def test_wells_and_filters_round_trip() -> None:
    rows = days(count=3, actual=1.0, predicted=1.0, well="A")
    rows += days(count=2, actual=1.0, predicted=1.0, well="B")
    r = result("m", rows)
    assert r.wells() == ("A", "B")
    assert len(r.for_well("A")) == 3
    with pytest.raises(ValidationError):
        r.evaluated = ()  # type: ignore[misc]


class TestModelGuards:
    """Model-level guards that only bite on data this field happens not to contain."""

    @staticmethod
    def _window(rates: list[float]) -> list[ClassifiedDay]:
        return [
            ClassifiedDay(
                day=ProductionDay(
                    well="W1",
                    production_date=dt.date(2010, 1, 1) + dt.timedelta(days=i),
                    on_stream_hours=24.0,
                    oil_volume_sm3=rate,
                    well_status=WellStatus.PRODUCING,
                    choke_size=50.0,
                    source="test",
                ),
                day_class=DayClass.VALID_PRODUCING,
            )
            for i, rate in enumerate(rates)
        ]

    def test_hyperbolic_refuses_a_window_too_steep_for_its_curvature(self) -> None:
        """Clamping instead produced a fitted value near 1e19 and a band that never triggers."""
        steep = [3000.0 * math.exp(-0.12 * i) for i in range(40)]
        assert HyperbolicDecline().fit(self._window(steep)) is None

    def test_hyperbolic_still_fits_a_gentle_decline(self) -> None:
        gentle = [3000.0 * math.exp(-0.002 * i) for i in range(40)]
        assert HyperbolicDecline().fit(self._window(gentle)) is not None

    def test_the_naive_baselines_do_not_widen_with_horizon(self) -> None:
        """Section 3 fixes their band; section 13 exempts them from amendment."""
        window = self._window([2000.0 + (i % 5) * 100 for i in range(30)])
        for model in (NaiveMedian28(), NaivePersistence()):
            fitted = model.fit(window)
            assert fitted is not None
            near, far = fitted.predict(1), fitted.predict(28)
            assert near.lower == pytest.approx(far.lower)
            assert near.upper == pytest.approx(far.upper)

    def test_a_candidate_band_does_widen_with_horizon(self) -> None:
        window = self._window([3000.0 * math.exp(-0.002 * i) for i in range(40)])
        fitted = ExponentialDecline().fit(window)
        assert fitted is not None
        assert fitted.predict(28).upper - fitted.predict(28).lower > (
            fitted.predict(1).upper - fitted.predict(1).lower
        )
