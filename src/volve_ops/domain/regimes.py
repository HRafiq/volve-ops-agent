"""Operating-regime segmentation and stable reference windows.

docs/eval_protocol.md section 7 defines a stable reference window by operational facts only:
no status change, choke within a tolerance of its median, no dated activity inside it, at least
twenty valid producing days, and no quarantined days. Nothing here may reference a residual, a
prediction or a detector output, because a window rule that can see how a model performed is a
rule that can be used to hide how a model performed.

Finding such windows is not quite a filter, because the choke test is relative to the window's
own median and so depends on the window. The approach is to cut the record at the breaks that
are unambiguous, then split any remaining segment that fails the choke test at its worst
offender and recurse. That is deterministic, terminates, and never merges across a break.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from itertools import pairwise
from statistics import median

from pydantic import BaseModel, ConfigDict

from volve_ops.domain.day_class import ClassifiedDay, DayClass

MIN_VALID_PRODUCING_DAYS = 20
CHOKE_RELATIVE_TOLERANCE = 0.10


class StableWindow(BaseModel):
    """A span of one wellbore's history that qualifies as a reference window."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    well: str
    start: dt.date
    end: dt.date
    valid_producing_days: int
    median_choke: float | None
    choke_test_applied: bool

    def contains(self, day: dt.date) -> bool:
        return self.start <= day <= self.end


def _is_break(day: ClassifiedDay, previous: ClassifiedDay | None, activity: set[dt.date]) -> bool:
    """Whether a day ends the segment before it.

    A quarantined day breaks a window because section 7 forbids one inside. A dated activity
    breaks it because the well was being worked on. A status change breaks it because the
    regime changed by definition.
    """
    if day.day_class is DayClass.QUARANTINED:
        return True
    if day.day.production_date in activity:
        return True
    return previous is not None and day.day.well_status is not previous.day.well_status


def _choke_values(segment: Sequence[ClassifiedDay]) -> list[float]:
    return [
        d.day.choke_size
        for d in segment
        if d.day_class is DayClass.VALID_PRODUCING and d.day.choke_size is not None
    ]


def _split_on_choke(
    segment: Sequence[ClassifiedDay], tolerance: float
) -> list[Sequence[ClassifiedDay]]:
    """Split a segment until every part holds its choke within tolerance of its own median.

    The cut goes at the largest step between consecutive readings, not at the day furthest
    from the median. A regime change is a step: the well was choked back on some date and
    stayed there. Cutting at the worst individual day instead peels one day off the end at a
    time and never finds the boundary, which leaves the two regimes it was meant to separate
    still joined.

    If the source carries no choke reading the test cannot run, and section 7 says the window
    then rests on status and activity alone.
    """
    values = _choke_values(segment)
    if len(values) < 2:
        return [segment]

    centre = median(values)
    if centre == 0.0:
        return [segment]

    within_tolerance = all(
        abs(d.day.choke_size - centre) / abs(centre) <= tolerance
        for d in segment
        if d.day_class is DayClass.VALID_PRODUCING and d.day.choke_size is not None
    )
    if within_tolerance:
        return [segment]

    readings = [
        (i, d.day.choke_size)
        for i, d in enumerate(segment)
        if d.day_class is DayClass.VALID_PRODUCING and d.day.choke_size is not None
    ]
    if len(readings) < 2:
        return [segment]

    cut_index, biggest_step = None, 0.0
    for (_, previous), (index, current) in pairwise(readings):
        step = abs(current - previous)
        if step > biggest_step:
            cut_index, biggest_step = index, step

    if cut_index is None or cut_index == 0:
        return [segment]

    out: list[Sequence[ClassifiedDay]] = []
    for part in (segment[:cut_index], segment[cut_index:]):
        if part:
            out.extend(_split_on_choke(part, tolerance))
    return out


def stable_reference_windows(
    days: Sequence[ClassifiedDay],
    *,
    activity_dates: set[dt.date] | None = None,
    min_valid_days: int = MIN_VALID_PRODUCING_DAYS,
    choke_tolerance: float = CHOKE_RELATIVE_TOLERANCE,
) -> list[StableWindow]:
    """Every qualifying stable reference window for one wellbore, in date order.

    `days` must be one wellbore's history. `activity_dates` are dates on which a drilling,
    intervention or completion record exists for the well; a window containing one is not
    stable. Activity is taken at well level rather than wellbore level, so that drilling a
    sidetrack disqualifies windows on its siblings, which is the conservative reading.
    """
    if not days:
        return []
    wells = {d.day.well for d in days}
    if len(wells) > 1:
        raise ValueError(f"expected one wellbore's history, got {sorted(wells)}")

    activity = activity_dates or set()
    ordered = sorted(days, key=lambda d: d.day.production_date)

    segments: list[list[ClassifiedDay]] = []
    current: list[ClassifiedDay] = []
    previous: ClassifiedDay | None = None
    for day in ordered:
        if _is_break(day, previous, activity):
            if current:
                segments.append(current)
            current = []
            previous = None if day.day_class is DayClass.QUARANTINED else day
            continue
        current.append(day)
        previous = day
    if current:
        segments.append(current)

    windows: list[StableWindow] = []
    for segment in segments:
        for part in _split_on_choke(segment, choke_tolerance):
            valid = [d for d in part if d.day_class is DayClass.VALID_PRODUCING]
            if len(valid) < min_valid_days:
                continue
            chokes = _choke_values(part)
            windows.append(
                StableWindow(
                    well=next(iter(wells)),
                    start=part[0].day.production_date,
                    end=part[-1].day.production_date,
                    valid_producing_days=len(valid),
                    median_choke=median(chokes) if chokes else None,
                    choke_test_applied=len(chokes) >= 2,
                )
            )
    return sorted(windows, key=lambda w: w.start)


def select_reference_window(
    windows: Sequence[StableWindow], before: dt.date
) -> StableWindow | None:
    """The window an expectation is fitted on for a candidate episode starting at `before`.

    Section 7's rule: the most recent qualifying window ending before the candidate's first
    day, taken at maximal extent. Without a rule the choice among qualifying windows would be
    free, and since the window sets the reference rate it would silently set the episode
    threshold too.
    """
    eligible = [w for w in windows if w.end < before]
    if not eligible:
        return None
    latest_end = max(w.end for w in eligible)
    tied = [w for w in eligible if w.end == latest_end]
    return max(tied, key=lambda w: (w.end - w.start).days)
