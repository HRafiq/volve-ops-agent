"""The temporal split, so that nothing can be fitted or selected on hold-out data by accident.

docs/eval_protocol.md section 10 fixes the hold-out as the most recent 25 percent of the
production record by calendar time, with a 90-day buffer carved out of the development side.
From the moment the boundary is known, every fit, backtest, label, curated case and threshold
choice uses pre-boundary data only.

This module exists because that rule is easy to honour in a document and easy to forget in a
loop over the whole history. Restricting the data at the source is harder to get wrong than
remembering to restrict it at every call site.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from volve_ops.domain.day_class import ClassifiedDay, DayClass

HOLD_OUT_FRACTION = 0.25
BUFFER_DAYS = 90
MIN_DEVELOPMENT_DAYS = 150


class TemporalSplit(BaseModel):
    """The boundary and buffer, derived from the record rather than configured."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_start: dt.date
    record_end: dt.date
    boundary: dt.date
    development_end: dt.date

    @property
    def span_days(self) -> int:
        return (self.record_end - self.record_start).days

    def is_development(self, day: dt.date) -> bool:
        """Strictly before the buffer. The buffer itself is used for neither purpose."""
        return day < self.development_end

    def is_hold_out(self, day: dt.date) -> bool:
        return day >= self.boundary


def derive_split(days: Sequence[ClassifiedDay]) -> TemporalSplit:
    """Compute the split from the production record.

    The record runs from the first to the last valid producing day across oil producers, so
    injection-only wells do not move the boundary.
    """
    dates = [d.day.production_date for d in days if d.day_class is DayClass.VALID_PRODUCING]
    if not dates:
        raise ValueError("no valid producing days, so no record to split")
    start, end = min(dates), max(dates)
    span = (end - start).days
    boundary = start + dt.timedelta(days=round(span * (1.0 - HOLD_OUT_FRACTION)))
    return TemporalSplit(
        record_start=start,
        record_end=end,
        boundary=boundary,
        development_end=boundary - dt.timedelta(days=BUFFER_DAYS),
    )


def development_only(
    days: Sequence[ClassifiedDay], split: TemporalSplit
) -> tuple[ClassifiedDay, ...]:
    """Just the development days. Anything a model is fitted or selected on goes through here."""
    return tuple(d for d in days if split.is_development(d.day.production_date))


def cold_start_wells(
    history_by_well: Mapping[str, Sequence[ClassifiedDay]], split: TemporalSplit
) -> tuple[str, ...]:
    """Wells with too little history before the buffer to be scored on the hold-out.

    In a field developed in stages a late well can have almost all of its life after the
    boundary, leaving nothing to fit on. Section 10 excludes those from hold-out scoring and
    reports them separately rather than letting them look like failures.
    """
    out = []
    for well, days in history_by_well.items():
        development = [
            d
            for d in days
            if d.day_class is DayClass.VALID_PRODUCING
            and split.is_development(d.day.production_date)
        ]
        if len(development) < MIN_DEVELOPMENT_DAYS:
            out.append(well)
    return tuple(sorted(out))
