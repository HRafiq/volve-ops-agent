"""The temporal split. This module exists because the rule is easy to forget in a loop."""

from __future__ import annotations

import datetime as dt

import pytest

from volve_ops.domain.day_class import ClassifiedDay, DayClass
from volve_ops.domain.splits import (
    BUFFER_DAYS,
    cold_start_wells,
    derive_split,
    development_only,
)
from volve_ops.ingest.production import ProductionDay, WellStatus


def producing(well: str, date: dt.date) -> ClassifiedDay:
    return ClassifiedDay(
        day=ProductionDay(
            well=well,
            production_date=date,
            on_stream_hours=24.0,
            oil_volume_sm3=2400.0,
            well_status=WellStatus.PRODUCING,
            source="test",
        ),
        day_class=DayClass.VALID_PRODUCING,
    )


def span(well: str, start: dt.date, days: int) -> list[ClassifiedDay]:
    return [producing(well, start + dt.timedelta(days=i)) for i in range(days)]


def test_the_boundary_is_the_most_recent_quarter_of_the_record() -> None:
    days = span("A", dt.date(2008, 1, 1), 401)  # 400-day span
    split = derive_split(days)
    assert split.record_start == dt.date(2008, 1, 1)
    assert split.span_days == 400
    assert split.boundary == dt.date(2008, 1, 1) + dt.timedelta(days=300)
    assert split.development_end == split.boundary - dt.timedelta(days=BUFFER_DAYS)


def test_the_buffer_belongs_to_neither_side() -> None:
    days = span("A", dt.date(2008, 1, 1), 401)
    split = derive_split(days)
    in_buffer = split.development_end + dt.timedelta(days=1)
    assert not split.is_development(in_buffer)
    assert not split.is_hold_out(in_buffer)


def test_development_only_excludes_everything_from_the_buffer_onward() -> None:
    days = span("A", dt.date(2008, 1, 1), 401)
    split = derive_split(days)
    kept = development_only(days, split)
    assert kept
    assert max(d.day.production_date for d in kept) < split.development_end
    assert all(not split.is_hold_out(d.day.production_date) for d in kept)


def test_only_valid_producing_days_define_the_record() -> None:
    """An injector must not move the boundary."""
    producers = span("A", dt.date(2010, 1, 1), 101)
    injector = ClassifiedDay(
        day=ProductionDay(
            well="B",
            production_date=dt.date(2020, 1, 1),
            on_stream_hours=24.0,
            well_status=WellStatus.INJECTING,
            source="test",
        ),
        day_class=DayClass.NON_PRODUCING,
    )
    split = derive_split([*producers, injector])
    assert split.record_end == dt.date(2010, 4, 11)


def test_a_record_with_no_valid_producing_days_cannot_be_split() -> None:
    with pytest.raises(ValueError, match="no valid producing days"):
        derive_split([])


def test_a_well_that_arrives_late_is_a_cold_start() -> None:
    """The protocol's reason: a late well can have almost all of its life after the boundary."""
    early = span("early", dt.date(2008, 1, 1), 1200)
    late = span("late", dt.date(2010, 6, 1), 200)
    split = derive_split([*early, *late])
    cold = cold_start_wells({"early": early, "late": late}, split)
    assert cold == ("late",)
