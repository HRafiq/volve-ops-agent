"""Day classification, rates, shortfall and deferred volume.

The partition is the thing most worth testing: every well-day must land in exactly one class,
and the ordering of the rules decides whether a shut-in well quietly accrues deferred volume
for the rest of the record.
"""

from __future__ import annotations

import datetime as dt
import itertools

import pytest
from pydantic import ValidationError

from volve_ops.domain.day_class import (
    HOURS_PER_DAY,
    ClassifiedDay,
    DayClass,
    classify,
    deferred_volume,
    expected_volume,
    rate_shortfall,
)
from volve_ops.ingest.production import CapacityLimits, ProductionDay, WellStatus

DATE = dt.date(2010, 6, 1)


def day(**over: object) -> ProductionDay:
    base: dict[str, object] = {"well": "15/9-F-12", "production_date": DATE, "source": "test"}
    base.update(over)
    return ProductionDay(**base)  # type: ignore[arg-type]


def cls(
    d: ProductionDay,
    *,
    columns: bool = True,
    cap: CapacityLimits | None = None,
    status_column: bool = False,
) -> ClassifiedDay:
    return classify(
        d,
        capacity=cap,
        gas_and_water_columns_present=columns,
        status_column_present=status_column,
    )


class TestPartition:
    @staticmethod
    def _expected_class(
        hours: float | None, oil: float | None, status: WellStatus | None
    ) -> DayClass:
        """Section 6's rules restated independently, so the test is not the code again."""
        oil_expected = status is None or status is WellStatus.PRODUCING
        if hours is None or (oil_expected and oil is None):
            return DayClass.MISSING
        if hours < 0.0 or hours > 24.0:
            return DayClass.QUARANTINED
        if oil is not None and oil < 0.0:
            return DayClass.QUARANTINED
        if hours == 0.0 and oil is not None and oil != 0.0:
            return DayClass.QUARANTINED
        if status is WellStatus.PRODUCING and hours > 0.0 and oil == 0.0:
            return DayClass.QUARANTINED  # no gas and no water in these fixtures
        if status is not None and status is not WellStatus.PRODUCING:
            return DayClass.NON_PRODUCING
        if hours == 0.0:
            return DayClass.DOWNTIME
        if hours < 6.0:
            return DayClass.PARTIAL
        return DayClass.VALID_PRODUCING

    def test_every_combination_lands_in_its_specified_class(self) -> None:
        """Walk the space and assert the class, not merely that one was returned.

        Asserting only that a DayClass came back is a tautology for a function that returns
        one, and would pass under any reordering of the rules. The expectation is restated
        from section 6 independently above.
        """
        hours = [None, 0.0, 0.1, 5.9, 6.0, 23.9, 24.0, 25.0, -1.0]
        oils = [None, -1.0, 0.0, 900.0]
        statuses = [None, WellStatus.PRODUCING, WellStatus.INJECTING, WellStatus.SHUT_IN]
        seen: set[DayClass] = set()
        for h, o, s in itertools.product(hours, oils, statuses):
            got = cls(day(on_stream_hours=h, oil_volume_sm3=o, well_status=s)).day_class
            want = self._expected_class(h, o, s)
            assert got is want, f"hours={h} oil={o} status={s}: got {got}, expected {want}"
            seen.add(got)
        assert seen == set(DayClass), f"classes never reached: {set(DayClass) - seen}"

    @pytest.mark.parametrize(
        ("hours", "expected"),
        [
            (0.0, DayClass.DOWNTIME),
            (0.1, DayClass.PARTIAL),
            (5.9, DayClass.PARTIAL),
            (6.0, DayClass.VALID_PRODUCING),
            (24.0, DayClass.VALID_PRODUCING),
        ],
    )
    def test_the_six_hour_boundary(self, hours: float, expected: DayClass) -> None:
        # Zero oil on the zero-hour case: a volume without hours is a quarantine failure,
        # which is a different rule and is covered separately.
        oil = 0.0 if hours == 0.0 else 100.0
        d = day(on_stream_hours=hours, oil_volume_sm3=oil, well_status=WellStatus.PRODUCING)
        assert cls(d).day_class is expected

    def test_absent_hours_is_missing_not_downtime(self) -> None:
        assert cls(day(oil_volume_sm3=100.0)).day_class is DayClass.MISSING

    def test_quarantine_is_tested_before_the_hour_classes(self) -> None:
        d = day(on_stream_hours=25.0, oil_volume_sm3=100.0, well_status=WellStatus.PRODUCING)
        assert cls(d).day_class is DayClass.QUARANTINED

    def test_non_producing_is_tested_before_downtime(self) -> None:
        """Otherwise a shut-in well accrues deferred volume for the rest of the record."""
        d = day(on_stream_hours=0.0, oil_volume_sm3=0.0, well_status=WellStatus.SHUT_IN)
        assert cls(d).day_class is DayClass.NON_PRODUCING


class TestProtocolV1Amendment:
    def test_an_injector_without_an_oil_volume_is_non_producing_not_missing(self) -> None:
        """Amendment 1. An injector has no oil volume by nature, not by omission."""
        d = day(on_stream_hours=24.0, well_status=WellStatus.INJECTING)
        assert cls(d).day_class is DayClass.NON_PRODUCING

    def test_a_producing_day_without_an_oil_volume_is_still_missing(self) -> None:
        d = day(on_stream_hours=24.0, well_status=WellStatus.PRODUCING)
        assert cls(d).day_class is DayClass.MISSING

    def test_an_impossible_injector_row_is_still_quarantined(self) -> None:
        """The amendment must not let a physically invalid row through as non-producing."""
        d = day(on_stream_hours=30.0, well_status=WellStatus.INJECTING)
        assert cls(d).day_class is DayClass.QUARANTINED

    def test_a_source_with_no_status_still_treats_absent_oil_as_missing(self) -> None:
        assert cls(day(on_stream_hours=24.0)).day_class is DayClass.MISSING


class TestNormalisedRate:
    def test_rate_is_defined_only_on_a_valid_producing_day(self) -> None:
        full = cls(
            day(on_stream_hours=12.0, oil_volume_sm3=900.0, well_status=WellStatus.PRODUCING)
        )
        assert full.q_24h == pytest.approx(1800.0)
        others = [
            day(on_stream_hours=2.0, oil_volume_sm3=150.0, well_status=WellStatus.PRODUCING),
            day(on_stream_hours=0.0, oil_volume_sm3=0.0, well_status=WellStatus.PRODUCING),
            day(on_stream_hours=24.0, well_status=WellStatus.INJECTING),
            day(oil_volume_sm3=100.0),
            day(on_stream_hours=30.0, oil_volume_sm3=100.0, well_status=WellStatus.PRODUCING),
        ]
        for d in others:
            c = cls(d)
            assert c.day_class is not DayClass.VALID_PRODUCING
            assert c.q_24h is None, f"{c.day_class} should have no rate"

    def test_a_full_producing_day_with_no_oil_has_a_rate_of_zero(self) -> None:
        d = day(
            on_stream_hours=24.0,
            oil_volume_sm3=0.0,
            gas_volume_sm3=500.0,
            water_volume_sm3=900.0,
            well_status=WellStatus.PRODUCING,
        )
        c = cls(d)
        assert c.day_class is DayClass.VALID_PRODUCING
        assert c.q_24h == 0.0


class TestVolumes:
    @pytest.mark.parametrize("hours", [0.0, 3.0, 6.0, 18.0, 24.0])
    def test_expected_and_deferred_are_complementary(self, hours: float) -> None:
        """They sum to q_expected for every day in scope, so nothing is double counted."""
        # Zero oil on the zero-hour case: oil without hours is a quarantine failure.
        oil = 0.0 if hours == 0.0 else 10.0
        c = cls(day(on_stream_hours=hours, oil_volume_sm3=oil, well_status=WellStatus.PRODUCING))
        e, f = expected_volume(c, 2400.0), deferred_volume(c, 2400.0)
        assert e is not None and f is not None
        assert e + f == pytest.approx(2400.0)

    def test_expected_volume_is_continuous_at_the_six_hour_boundary(self) -> None:
        below = cls(
            day(on_stream_hours=5.999, oil_volume_sm3=10.0, well_status=WellStatus.PRODUCING)
        )
        above = cls(day(on_stream_hours=6.0, oil_volume_sm3=10.0, well_status=WellStatus.PRODUCING))
        assert below.day_class is DayClass.PARTIAL
        assert above.day_class is DayClass.VALID_PRODUCING
        e_below, e_above = expected_volume(below, 2400.0), expected_volume(above, 2400.0)
        assert e_below is not None and e_above is not None
        assert abs(e_above - e_below) == pytest.approx(0.1, abs=0.01)

    def test_a_shut_in_day_carries_no_expectation_at_all(self) -> None:
        c = cls(day(on_stream_hours=24.0, oil_volume_sm3=0.0, well_status=WellStatus.SHUT_IN))
        assert expected_volume(c, 2400.0) is None
        assert deferred_volume(c, 2400.0) is None
        assert rate_shortfall(c, 2400.0) is None

    def test_downtime_defers_a_whole_day_and_shortfalls_nothing(self) -> None:
        c = cls(day(on_stream_hours=0.0, oil_volume_sm3=0.0, well_status=WellStatus.PRODUCING))
        assert deferred_volume(c, 2400.0) == pytest.approx(2400.0)
        assert rate_shortfall(c, 2400.0) == pytest.approx(0.0)

    def test_a_partial_day_contributes_volume_but_not_a_rate(self) -> None:
        """The asymmetry the protocol calls load-bearing, pinned so it cannot drift.

        A partial day has no trustworthy rate, so q_24h is None, but its volume is real and
        still counts toward a window's shortfall.
        """
        c = cls(day(on_stream_hours=3.0, oil_volume_sm3=200.0, well_status=WellStatus.PRODUCING))
        assert c.day_class is DayClass.PARTIAL
        assert c.q_24h is None
        assert rate_shortfall(c, 2400.0) == pytest.approx(2400.0 * 3 / HOURS_PER_DAY - 200.0)

    def test_overproduction_is_a_negative_shortfall_rather_than_clipped(self) -> None:
        c = cls(day(on_stream_hours=24.0, oil_volume_sm3=3000.0, well_status=WellStatus.PRODUCING))
        s = rate_shortfall(c, 2400.0)
        assert s is not None and s < 0

    def test_capacity_quarantine_applies_when_a_limit_exists(self) -> None:
        d = day(on_stream_hours=24.0, oil_volume_sm3=50_000.0, well_status=WellStatus.PRODUCING)
        assert cls(d).day_class is DayClass.VALID_PRODUCING
        assert cls(d, cap=CapacityLimits(oil_sm3=10_000.0)).day_class is DayClass.QUARANTINED


def test_classified_days_are_immutable() -> None:
    c = cls(day(on_stream_hours=24.0, oil_volume_sm3=900.0, well_status=WellStatus.PRODUCING))
    assert isinstance(c, ClassifiedDay)
    with pytest.raises(ValidationError):
        c.day_class = DayClass.MISSING  # type: ignore[misc]
