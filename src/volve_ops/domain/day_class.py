"""Day classification, normalised rate, shortfall and deferred volume.

This implements docs/eval_protocol.md section 6 exactly, at protocol v1. That document is
pre-registered and public; where this module and it disagree, the document is the
specification and this module is the bug.

The ordering of the classes is load-bearing and is not an implementation detail:

- missing is tested first, so an absent value is never read as a zero;
- quarantine is tested next, so a physically impossible row cannot reach a class that would
  make it look like ordinary production;
- non-producing is tested before the hour-based classes, so a well that was shut in or
  converted to injection is never read as downtime on a producing well, which would otherwise
  accrue deferred volume against it for the rest of the record.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from volve_ops.ingest.production import (
    CapacityLimits,
    ProductionDay,
    WellStatus,
    physical_checks,
)
from volve_ops.ingest.quarantine import QuarantineReason

# docs/eval_protocol.md section 6. Below this, the 24/hours multiplier scales measurement
# error, allocation error and start-up ramp by more than four, and the result stops being
# comparable to a full-day rate.
MIN_PRODUCING_HOURS = 6.0
HOURS_PER_DAY = 24.0


class DayClass(StrEnum):
    """Exactly one of these applies to every well-day. Values are stable; they are persisted."""

    MISSING = "missing"
    QUARANTINED = "quarantined"
    NON_PRODUCING = "non_producing"
    DOWNTIME = "downtime"
    PARTIAL = "partial"
    VALID_PRODUCING = "valid_producing"


# Classes that carry an expectation. A day outside this set gets no expected volume, so it
# contributes nothing to either of the two sums below.
IN_SCOPE_FOR_EXPECTATION = frozenset(
    {DayClass.DOWNTIME, DayClass.PARTIAL, DayClass.VALID_PRODUCING}
)


class ClassifiedDay(BaseModel):
    """A well-day with its class, and the reasons if it was quarantined."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: ProductionDay
    day_class: DayClass
    quarantine_reasons: tuple[QuarantineReason, ...] = ()
    checks_not_evaluated: tuple[QuarantineReason, ...] = ()

    @property
    def q_24h(self) -> float | None:
        """Normalised producing rate in Sm3/d, defined only on a valid producing day.

        None elsewhere, deliberately. A partial day has a volume but no trustworthy rate, and
        returning a number for it would invite exactly the extrapolation the 6-hour floor
        exists to prevent.
        """
        if self.day_class is not DayClass.VALID_PRODUCING:
            return None
        hours, oil = self.day.on_stream_hours, self.day.oil_volume_sm3
        if hours is None or oil is None or hours <= 0.0:  # pragma: no cover - class guarantees
            return None
        return oil / hours * HOURS_PER_DAY


def classify(
    day: ProductionDay,
    *,
    capacity: CapacityLimits | None,
    gas_and_water_columns_present: bool,
    status_column_present: bool,
) -> ClassifiedDay:
    """Assign exactly one class, by the first rule in section 6 that matches.

    status_column_present says whether the source carries a well-status field at all. The
    protocol treats a null status on a row of a source that has the column as a gap in the
    record, and a source with no such column as a different situation with its own fallback.
    A None status alone cannot tell those apart, so the caller states which it is.
    """
    hours = day.on_stream_hours

    # 1. Missing. A null status counts, where the source has a status field at all, because a
    #    per-row null is a gap in the record and not a statement that the well was idle.
    #
    #    The oil-volume test is qualified by status (protocol v1, amendment 1). An injector
    #    has no oil volume by nature rather than by omission, and testing it unconditionally
    #    classed every injector day as a gap in the record.
    if status_column_present and day.well_status is None:
        return ClassifiedDay(day=day, day_class=DayClass.MISSING)

    oil_is_expected = day.well_status is None or day.well_status is WellStatus.PRODUCING
    if hours is None or (oil_is_expected and day.oil_volume_sm3 is None):
        return ClassifiedDay(day=day, day_class=DayClass.MISSING)

    # 2. Quarantined.
    outcome = physical_checks(
        day, capacity=capacity, gas_and_water_columns_present=gas_and_water_columns_present
    )
    if outcome.failures:
        return ClassifiedDay(
            day=day,
            day_class=DayClass.QUARANTINED,
            quarantine_reasons=outcome.failures,
            checks_not_evaluated=outcome.not_evaluated,
        )

    # 3. Non-producing, before the hour-based classes.
    if day.well_status is not None and day.well_status is not WellStatus.PRODUCING:
        return ClassifiedDay(
            day=day, day_class=DayClass.NON_PRODUCING, checks_not_evaluated=outcome.not_evaluated
        )

    # 4, 5, 6.
    if hours == 0.0:
        day_class = DayClass.DOWNTIME
    elif hours < MIN_PRODUCING_HOURS:
        day_class = DayClass.PARTIAL
    else:
        day_class = DayClass.VALID_PRODUCING
    return ClassifiedDay(day=day, day_class=day_class, checks_not_evaluated=outcome.not_evaluated)


def expected_volume(classified: ClassifiedDay, q_expected: float) -> float | None:
    """Expected volume for a day, pro rata on its producing hours.

    `q_expected * min(hours, 24) / 24`, so downtime contributes nothing, a partial day
    contributes in proportion, and there is no discontinuity at the 6-hour boundary. None for
    a day that carries no expectation.
    """
    if classified.day_class not in IN_SCOPE_FOR_EXPECTATION:
        return None
    hours = classified.day.on_stream_hours
    if hours is None:  # pragma: no cover - the in-scope classes guarantee a value
        return None
    return q_expected * min(hours, HOURS_PER_DAY) / HOURS_PER_DAY


def deferred_volume(classified: ClassifiedDay, q_expected: float) -> float | None:
    """Volume not produced because the well was not flowing.

    Complementary to expected_volume by construction: the two sum to q_expected for every day
    in scope, so nothing is double counted and nothing falls between them.

    This is an estimate and is reported as one. It is never added to rate shortfall to make a
    single headline number, because a well shut in for half a month has a large deferred
    volume and may have no rate shortfall at all, and an investigation should be able to say
    exactly that.
    """
    if classified.day_class not in IN_SCOPE_FOR_EXPECTATION:
        return None
    hours = classified.day.on_stream_hours
    if hours is None:  # pragma: no cover - the in-scope classes guarantee a value
        return None
    return q_expected * (HOURS_PER_DAY - min(hours, HOURS_PER_DAY)) / HOURS_PER_DAY


def rate_shortfall(classified: ClassifiedDay, q_expected: float) -> float | None:
    """Production lost while the well was flowing: expected volume minus actual.

    Positive means the well produced less than expected over the hours it was on stream.
    Negative means it produced more, which is kept rather than clipped so that a window's sum
    is an honest total rather than a one-sided one.
    """
    expected = expected_volume(classified, q_expected)
    if expected is None:
        return None
    actual = classified.day.oil_volume_sm3
    if actual is None:  # pragma: no cover - the in-scope classes guarantee a value
        return None
    return expected - actual
