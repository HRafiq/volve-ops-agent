"""Sustained underperformance episodes.

docs/eval_protocol.md section 9. An episode is not a calendar period and not a single bad day;
it is a run of valid producing days below the expectation's lower edge, long enough and costly
enough to be worth a reviewer's attention.

The window tolerates short recoveries. Production that recovers for a day and drops again is
one problem, not two, and three consecutive days back inside the band is the smallest run that
distinguishes a recovery from noise. That is why the window can be longer than the run that
triggered it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from statistics import median

from pydantic import BaseModel, ConfigDict

from volve_ops.domain.day_class import ClassifiedDay, DayClass, deferred_volume, rate_shortfall
from volve_ops.domain.expectation import ExpectationModel, FittedExpectation
from volve_ops.domain.regimes import StableWindow

MIN_TRIGGER_RUN = 7
MIN_WINDOW_VALID_DAYS = 10
RECOVERY_RUN = 3
SHORTFALL_FRACTION = 0.15
POORLY_EVIDENCED_FRACTION = 1.0 / 3.0


class Episode(BaseModel):
    """One opened episode, with everything needed to explain why it opened."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    well: str
    onset: dt.date
    offset: dt.date
    valid_producing_days: int
    trigger_run_days: int
    cumulative_rate_shortfall_sm3: float
    deferred_volume_sm3: float
    shortfall_threshold_sm3: float
    reference_rate_sm3_per_day: float
    gap_fraction: float
    open_ended: bool

    @property
    def poorly_evidenced(self) -> bool:
        """Too much of the window is quarantined or missing to call this detected."""
        return self.gap_fraction > POORLY_EVIDENCED_FRACTION


def detect_episodes(
    well: str,
    days: Sequence[ClassifiedDay],
    expectation: FittedExpectation,
    reference_rate: float,
) -> list[Episode]:
    """Open an episode wherever all four of section 9's conditions hold.

    `expectation` is fitted on the stable reference window selected by section 7, and
    `reference_rate` is that window's median rate, which scales the volume threshold.
    """
    ordered = sorted(days, key=lambda d: d.day.production_date)
    valid_positions = [i for i, d in enumerate(ordered) if d.day_class is DayClass.VALID_PRODUCING]
    if not valid_positions:
        return []

    # Below-band state for each valid producing day, in sequence order.
    below: list[bool] = []
    for step, index in enumerate(valid_positions, start=1):
        day = ordered[index]
        rate = day.q_24h
        prediction = expectation.predict(step, choke=day.day.choke_size)
        below.append(rate is not None and rate < prediction.lower)

    episodes: list[Episode] = []
    cursor = 0
    while cursor < len(below):
        if not below[cursor]:
            cursor += 1
            continue

        run_end = cursor
        while run_end + 1 < len(below) and below[run_end + 1]:
            run_end += 1
        run_length = run_end - cursor + 1
        if run_length < MIN_TRIGGER_RUN:
            cursor = run_end + 1
            continue

        # Extend through short recoveries until three consecutive days sit back inside.
        last_below = run_end
        scan = run_end + 1
        while scan < len(below):
            if below[scan]:
                last_below = scan
                scan += 1
                continue
            recovery = 0
            while scan < len(below) and not below[scan] and recovery < RECOVERY_RUN:
                recovery += 1
                scan += 1
            if recovery >= RECOVERY_RUN:
                break
        open_ended = scan >= len(below) and last_below == len(below) - 1

        first_index = valid_positions[cursor]
        last_index = valid_positions[last_below]
        window = ordered[first_index : last_index + 1]
        window_valid = [d for d in window if d.day_class is DayClass.VALID_PRODUCING]
        if len(window_valid) < MIN_WINDOW_VALID_DAYS:
            cursor = last_below + 1
            continue

        shortfall = 0.0
        deferred = 0.0
        for offset, day in enumerate(window):
            step = (
                cursor
                + 1
                + sum(1 for d in window[:offset] if d.day_class is DayClass.VALID_PRODUCING)
            )
            q = expectation.predict(step, choke=day.day.choke_size).q_expected
            s = rate_shortfall(day, q)
            f = deferred_volume(day, q)
            if s is not None:
                shortfall += s
            if f is not None:
                deferred += f

        threshold = SHORTFALL_FRACTION * reference_rate * len(window_valid)
        if shortfall < threshold:
            cursor = last_below + 1
            continue

        gaps = sum(1 for d in window if d.day_class in (DayClass.QUARANTINED, DayClass.MISSING))
        episodes.append(
            Episode(
                well=well,
                onset=window[0].day.production_date,
                offset=window[-1].day.production_date,
                valid_producing_days=len(window_valid),
                trigger_run_days=run_length,
                cumulative_rate_shortfall_sm3=shortfall,
                deferred_volume_sm3=deferred,
                shortfall_threshold_sm3=threshold,
                reference_rate_sm3_per_day=reference_rate,
                gap_fraction=gaps / len(window) if window else 0.0,
                open_ended=open_ended,
            )
        )
        cursor = last_below + 1

    return episodes


def reference_rate_of(window_days: Sequence[ClassifiedDay]) -> float | None:
    """Median normalised rate of a stable reference window, which scales the threshold."""
    rates = [
        d.q_24h
        for d in window_days
        if d.day_class is DayClass.VALID_PRODUCING and d.q_24h is not None
    ]
    return median(rates) if rates else None


def sweep_well(
    well: str,
    days: Sequence[ClassifiedDay],
    windows: Sequence[StableWindow],
    model: ExpectationModel,
) -> list[Episode]:
    """Detect episodes across a well's history, refitting from the nearest preceding window.

    Section 7 fixes the expectation for a candidate episode as the most recent qualifying
    stable window ending before it. That matters more than it sounds: an expectation fitted
    once and carried across years of history is not the expectation the protocol describes,
    and because the interval widens with the horizon it becomes so wide that nothing can fall
    outside it. Each window therefore governs only the span until the next one begins.
    """
    ordered = sorted(days, key=lambda d: d.day.production_date)
    in_order = sorted(windows, key=lambda w: w.start)
    episodes: list[Episode] = []

    for position, window in enumerate(in_order):
        next_start = in_order[position + 1].start if position + 1 < len(in_order) else None
        in_window = [d for d in ordered if window.start <= d.day.production_date <= window.end]
        fitted = model.fit(in_window)
        reference = reference_rate_of(in_window)
        if fitted is None or reference is None:
            continue

        governed = [
            d
            for d in ordered
            if d.day.production_date > window.end
            and (next_start is None or d.day.production_date < next_start)
        ]
        if governed:
            episodes.extend(detect_episodes(well, governed, fitted, reference))

    return episodes
