"""Canonical production records, strictness, physical checks and duplicate handling."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from volve_ops import INGEST_VERSION
from volve_ops.ingest.production import (
    MATERIAL_FIELDS,
    CapacityLimits,
    CheckOutcome,
    ProductionDay,
    WellStatus,
    collapse_duplicates,
    physical_checks,
)
from volve_ops.ingest.quarantine import QuarantineReason

DATE = dt.date(2010, 6, 1)
NUMERIC_FIELDS = (
    "on_stream_hours",
    "oil_volume_sm3",
    "gas_volume_sm3",
    "water_volume_sm3",
    "choke_size",
)


def day(**overrides: object) -> ProductionDay:
    base: dict[str, object] = {
        "well": "15/9-F-1",
        "production_date": DATE,
        "source": "production.daily",
    }
    base.update(overrides)
    return ProductionDay(**base)  # type: ignore[arg-type]


def checks(
    d: ProductionDay, *, columns: bool = True, capacity: CapacityLimits | None = None
) -> CheckOutcome:
    return physical_checks(d, capacity=capacity, gas_and_water_columns_present=columns)


class TestStrictness:
    def test_numeric_string_is_not_parsed_into_a_float(self) -> None:
        with pytest.raises(ValidationError):
            day(on_stream_hours="5.0")

    def test_unexpected_column_is_an_error_not_a_silent_drop(self) -> None:
        with pytest.raises(ValidationError):
            day(unexpected_column=1.0)

    def test_a_raw_source_status_string_is_rejected_even_when_it_spells_a_member(self) -> None:
        """Source vocabularies must be mapped to WellStatus before a record is built."""
        with pytest.raises(ValidationError):
            day(well_status="producing")
        with pytest.raises(ValidationError):
            day(well_status="on stream")
        assert day(well_status=WellStatus.PRODUCING).well_status is WellStatus.PRODUCING

    def test_records_are_immutable(self) -> None:
        with pytest.raises(ValidationError):
            day(on_stream_hours=12.0).on_stream_hours = 13.0  # type: ignore[misc]

    def test_parser_version_defaults_to_the_module_constant(self) -> None:
        """A run manifest must not be able to record a version the code did not produce."""
        assert day().parser_version == INGEST_VERSION


class TestNonFiniteFloatsAreRejected:
    @pytest.mark.parametrize("field", NUMERIC_FIELDS)
    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_nan_and_infinity_cannot_enter_any_numeric_field(self, field: str, bad: float) -> None:
        """A spreadsheet reader yields NaN for a blank cell.

        A NaN here would be neither missing nor quarantined: it fails every comparison in
        physical_checks, falls through every day class, and then poisons every later sum.
        """
        with pytest.raises(ValidationError):
            day(**{field: bad})


class TestMissingIsNotZero:
    def test_absent_quantities_stay_none(self) -> None:
        d = day()
        assert d.on_stream_hours is None
        assert d.oil_volume_sm3 is None
        assert d.well_status is None

    def test_a_missing_hour_count_fails_no_physical_check(self) -> None:
        """Absence is not a defect. It is recorded and excluded, not quarantined."""
        assert checks(day(oil_volume_sm3=100.0)).failures == ()

    def test_measured_zero_is_distinguishable_from_missing(self) -> None:
        assert day(on_stream_hours=0.0).on_stream_hours == 0.0
        assert day().on_stream_hours is None


class TestPhysicalChecks:
    @pytest.mark.parametrize("hours", [-0.5, 24.5, 48.0])
    def test_hours_outside_a_day_are_quarantined(self, hours: float) -> None:
        assert QuarantineReason.HOURS_OUT_OF_RANGE in checks(day(on_stream_hours=hours)).failures

    @pytest.mark.parametrize("hours", [0.0, 0.1, 6.0, 24.0])
    def test_hours_inside_a_day_pass(self, hours: float) -> None:
        assert (
            QuarantineReason.HOURS_OUT_OF_RANGE not in checks(day(on_stream_hours=hours)).failures
        )

    def test_negative_volume_is_quarantined(self) -> None:
        failures = checks(day(on_stream_hours=12.0, oil_volume_sm3=-1.0)).failures
        assert QuarantineReason.NEGATIVE_VOLUME in failures

    def test_oil_without_any_on_stream_time_is_quarantined(self) -> None:
        failures = checks(day(on_stream_hours=0.0, oil_volume_sm3=50.0)).failures
        assert QuarantineReason.VOLUME_WITHOUT_HOURS in failures

    def test_a_negative_oil_volume_on_a_zero_hour_day_trips_both_reasons(self) -> None:
        """Section 7 says nonzero, which includes negative."""
        failures = checks(day(on_stream_hours=0.0, oil_volume_sm3=-5.0)).failures
        assert QuarantineReason.VOLUME_WITHOUT_HOURS in failures
        assert QuarantineReason.NEGATIVE_VOLUME in failures

    def test_a_producing_day_with_no_fluids_at_all_is_quarantined(self) -> None:
        failures = checks(
            day(
                on_stream_hours=24.0,
                oil_volume_sm3=0.0,
                gas_volume_sm3=0.0,
                water_volume_sm3=0.0,
                well_status=WellStatus.PRODUCING,
            )
        ).failures
        assert QuarantineReason.NO_FLUIDS_ON_PRODUCING_DAY in failures

    @pytest.mark.parametrize(
        ("gas", "water"),
        [(None, None), (0.0, None), (None, 0.0)],
    )
    def test_an_absent_gas_or_water_value_is_absence_of_corroboration(
        self, gas: float | None, water: float | None
    ) -> None:
        """A null is what a recording gap looks like, so it must not rescue the day.

        If a null counted as corroboration, an uncorroborated zero-oil day would become a
        valid producing day with zero oil, which the protocol reads as a genuine
        underperformance signal. That inversion is what this check exists to prevent.
        """
        failures = checks(
            day(
                on_stream_hours=24.0,
                oil_volume_sm3=0.0,
                gas_volume_sm3=gas,
                water_volume_sm3=water,
                well_status=WellStatus.PRODUCING,
            )
        ).failures
        assert QuarantineReason.NO_FLUIDS_ON_PRODUCING_DAY in failures

    def test_zero_oil_survives_when_gas_or_water_corroborates_it(self) -> None:
        """The signal the protocol protects: a full producing day that made no oil."""
        outcome = checks(
            day(
                on_stream_hours=24.0,
                oil_volume_sm3=0.0,
                gas_volume_sm3=500.0,
                water_volume_sm3=900.0,
                well_status=WellStatus.PRODUCING,
            )
        )
        assert outcome.failures == ()

    def test_an_injector_with_no_produced_fluids_is_not_quarantined(self) -> None:
        """Without the status qualifier, every injection day would be quarantined."""
        outcome = checks(
            day(
                on_stream_hours=24.0,
                oil_volume_sm3=0.0,
                gas_volume_sm3=0.0,
                water_volume_sm3=0.0,
                well_status=WellStatus.INJECTING,
            )
        )
        assert outcome.failures == ()

    def test_absent_gas_and_water_columns_report_the_check_as_not_evaluated(self) -> None:
        """A dropped check must be disclosable, not invisible."""
        outcome = checks(
            day(on_stream_hours=24.0, oil_volume_sm3=0.0, well_status=WellStatus.PRODUCING),
            columns=False,
        )
        assert outcome.failures == ()
        assert QuarantineReason.NO_FLUIDS_ON_PRODUCING_DAY in outcome.not_evaluated

    def test_capacity_is_reported_as_not_evaluated_until_a_figure_exists(self) -> None:
        outcome = checks(day(on_stream_hours=24.0, oil_volume_sm3=1e9))
        assert outcome.failures == ()
        assert QuarantineReason.VOLUME_ABOVE_CAPACITY in outcome.not_evaluated

    def test_capacity_bounds_are_per_fluid(self) -> None:
        """One shared scalar set from an oil figure would quarantine every day on its gas."""
        limits = CapacityLimits(oil_sm3=5_000.0, gas_sm3=2_000_000.0)
        ordinary = day(on_stream_hours=24.0, oil_volume_sm3=2_000.0, gas_volume_sm3=900_000.0)
        assert checks(ordinary, capacity=limits).failures == ()

        implausible_oil = day(on_stream_hours=24.0, oil_volume_sm3=50_000.0)
        failures = checks(implausible_oil, capacity=limits).failures
        assert QuarantineReason.VOLUME_ABOVE_CAPACITY in failures

    def test_a_day_can_fail_several_checks_at_once(self) -> None:
        failures = checks(day(on_stream_hours=30.0, oil_volume_sm3=-5.0)).failures
        assert QuarantineReason.HOURS_OUT_OF_RANGE in failures
        assert QuarantineReason.NEGATIVE_VOLUME in failures


class TestDuplicateHandling:
    def test_identical_duplicates_collapse_to_one(self) -> None:
        rows = [day(on_stream_hours=24.0, oil_volume_sm3=100.0)] * 2
        kept, conflicts = collapse_duplicates(rows)
        assert len(kept) == 1
        assert conflicts == []

    def test_the_surviving_row_does_not_depend_on_input_order(self) -> None:
        """Provenance is the point of keeping source, so it cannot be set by read order."""
        a = day(on_stream_hours=24.0, oil_volume_sm3=100.0, source="sheet-a")
        b = day(on_stream_hours=24.0, oil_volume_sm3=100.0, source="sheet-b")
        forward, _ = collapse_duplicates([a, b])
        reverse, _ = collapse_duplicates([b, a])
        assert forward[0].source == reverse[0].source == "sheet-a"

    def test_disagreeing_duplicates_name_the_fields_they_disagree_on(self) -> None:
        rows = [
            day(on_stream_hours=24.0, oil_volume_sm3=100.0),
            day(on_stream_hours=24.0, oil_volume_sm3=180.0),
        ]
        kept, conflicts = collapse_duplicates(rows)
        assert kept == []
        assert len(conflicts) == 1
        assert conflicts[0].disagreeing_fields == ("oil_volume_sm3",)
        assert conflicts[0].reason is QuarantineReason.DUPLICATE_DISAGREEMENT
        assert len(conflicts[0].rows) == 2

    def test_three_pairwise_disagreeing_rows_all_go_to_quarantine(self) -> None:
        rows = [day(oil_volume_sm3=v, on_stream_hours=24.0) for v in (100.0, 150.0, 200.0)]
        kept, conflicts = collapse_duplicates(rows)
        assert kept == []
        assert len(conflicts[0].rows) == 3

    def test_a_majority_does_not_win_because_a_vote_would_be_an_unregistered_repair(self) -> None:
        rows = [
            day(on_stream_hours=24.0, oil_volume_sm3=100.0),
            day(on_stream_hours=24.0, oil_volume_sm3=100.0),
            day(on_stream_hours=24.0, oil_volume_sm3=999.0),
        ]
        kept, conflicts = collapse_duplicates(rows)
        assert kept == []
        assert len(conflicts) == 1

    def test_a_value_against_a_null_counts_as_disagreement(self) -> None:
        rows = [
            day(on_stream_hours=24.0, gas_volume_sm3=500.0),
            day(on_stream_hours=24.0, gas_volume_sm3=None),
        ]
        kept, conflicts = collapse_duplicates(rows)
        assert kept == []
        assert conflicts[0].disagreeing_fields == ("gas_volume_sm3",)

    def test_disagreement_in_an_unused_column_does_not_discard_the_day(self) -> None:
        """Only material columns count. A usable day is not thrown away over metadata."""
        rows = [
            day(on_stream_hours=24.0, oil_volume_sm3=100.0, source="sheet-a"),
            day(on_stream_hours=24.0, oil_volume_sm3=100.0, source="sheet-b"),
        ]
        kept, conflicts = collapse_duplicates(rows)
        assert len(kept) == 1
        assert conflicts == []

    def test_a_choke_unit_disagreement_is_material(self) -> None:
        """30 mm and 30 percent describe different wells."""
        assert "choke_unit" in MATERIAL_FIELDS
        rows = [
            day(on_stream_hours=24.0, choke_size=30.0, choke_unit="mm"),
            day(on_stream_hours=24.0, choke_size=30.0, choke_unit="%"),
        ]
        kept, conflicts = collapse_duplicates(rows)
        assert kept == []
        assert conflicts[0].disagreeing_fields == ("choke_unit",)

    def test_distinct_wells_and_dates_are_untouched(self) -> None:
        rows = [
            day(well="A", on_stream_hours=24.0),
            day(well="B", on_stream_hours=24.0),
            day(well="A", production_date=dt.date(2010, 6, 2), on_stream_hours=24.0),
        ]
        kept, conflicts = collapse_duplicates(rows)
        assert conflicts == []
        assert [(d.well, d.production_date) for d in kept] == [
            ("A", DATE),
            ("A", dt.date(2010, 6, 2)),
            ("B", DATE),
        ]
