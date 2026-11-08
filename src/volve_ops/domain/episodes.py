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
from volve_ops.domain.sensors import Channel, reading

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
        recovered = False
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
                recovered = True
                break
        # Open-ended means no qualifying recovery was ever seen, whether the record ended on a
        # below-band day or part-way through a recovery too short to close the episode. Testing
        # whether the last day happened to be below the band answers a different question.
        open_ended = not recovered

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


class SeriesPoint(BaseModel):
    """One day of the chart the console draws, as the detector saw it.

    Exposed from here rather than assembled where it is displayed. Protocol section 21.1 confines
    the console to rendering, and the expected rate and its band are not a reading: they are the
    output of the model section 7 selected, fitted on the window section 7 chose, evaluated at the
    step count the detector used. A serving layer that recomputed any of those three would be a
    second detector, and the one thing this project has learned to distrust is a second
    implementation that nobody compares against the first.

    `expected`, `lower` and `upper` are None on a day that is not a valid producing day, because the
    model predicts per valid producing day and interpolating across a shut-in would draw a line the
    detector never evaluated.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    date: dt.date
    day_class: DayClass
    actual_rate_sm3_per_day: float | None
    expected: float | None
    lower: float | None
    upper: float | None
    below_band: bool
    on_stream_hours: float | None
    choke_size: float | None
    downhole_pressure_bar: float | None
    wellhead_pressure_bar: float | None
    water_cut: float | None
    governing_window_start: dt.date
    governing_window_end: dt.date


def sweep_series(
    well: str,
    days: Sequence[ClassifiedDay],
    windows: Sequence[StableWindow],
    model: ExpectationModel,
) -> list[SeriesPoint]:
    """The per-day series behind every episode this sweep would open.

    Deliberately a near-duplicate of `sweep_well`'s loop structure, and the duplication is the
    point of the test that pins them together: the step count, the governing window and the
    below-band decision must be the ones the detector used, or the chart shows a band the verdict
    was not judged against.

    The property the test asserts is the one that actually holds, measured rather than assumed:
    every episode's onset day is below band here, and so is each of the first `MIN_TRIGGER_RUN`
    valid producing days from onset. **Not** every day in the window, because section 9 extends an
    episode through short recoveries, so a window legitimately contains days back inside the band.
    Asserting the stronger property would have failed on 5 of the 14 development episodes, and
    writing it down before checking is how this project has published figures it had to retract.
    """
    ordered = sorted(days, key=lambda d: d.day.production_date)
    in_order = sorted(windows, key=lambda w: w.start)
    points: list[SeriesPoint] = []

    for position, window in enumerate(in_order):
        next_end = in_order[position + 1].end if position + 1 < len(in_order) else None
        in_window = [d for d in ordered if window.start <= d.day.production_date <= window.end]
        fitted = model.fit(in_window)
        reference = reference_rate_of(in_window)
        if fitted is None or reference is None:
            continue
        governed = [
            d
            for d in ordered
            if d.day.production_date > window.end
            and (next_end is None or d.day.production_date <= next_end)
        ]
        step = 0
        for entry in governed:
            prediction = None
            if entry.day_class is DayClass.VALID_PRODUCING:
                step += 1
                prediction = fitted.predict(step, choke=entry.day.choke_size)
            rate = entry.q_24h
            water = entry.day.water_volume_sm3
            oil = entry.day.oil_volume_sm3
            # Water cut only on a valid producing day, the same restriction as `expected` above and
            # for the same reason. A first version computed it on every governed day and published
            # four negative water cuts, down to -2.61, on days the classifier had already
            # quarantined with `negative_volume`. The volumes are real entries in the workbook, and
            # a day the day classifier refuses is a day nothing may be derived from: deriving a
            # ratio from it republishes as a figure what section 6 declined to treat as a reading.
            # A zero total is also excluded, because that is no flow rather than zero water cut.
            water_cut = (
                water / (water + oil)
                if entry.day_class is DayClass.VALID_PRODUCING
                and water is not None
                and oil is not None
                and water + oil > 0.0
                else None
            )
            points.append(
                SeriesPoint(
                    date=entry.day.production_date,
                    day_class=entry.day_class,
                    actual_rate_sm3_per_day=rate,
                    expected=None if prediction is None else prediction.q_expected,
                    lower=None if prediction is None else prediction.lower,
                    upper=None if prediction is None else prediction.upper,
                    below_band=(
                        prediction is not None and rate is not None and rate < prediction.lower
                    ),
                    on_stream_hours=entry.day.on_stream_hours,
                    choke_size=entry.day.choke_size,
                    downhole_pressure_bar=reading(entry.day, Channel.DOWNHOLE_PRESSURE),
                    wellhead_pressure_bar=reading(entry.day, Channel.WELLHEAD_PRESSURE),
                    water_cut=water_cut,
                    governing_window_start=window.start,
                    governing_window_end=window.end,
                )
            )
    return points


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
        # A candidate inside the next window is still governed by this one: section 7 selects
        # the most recent window *ending* before the candidate, and the next window has not
        # ended yet. Stopping at the next window's start would leave every day inside a window
        # unscanned by any sweep.
        next_end = in_order[position + 1].end if position + 1 < len(in_order) else None
        in_window = [d for d in ordered if window.start <= d.day.production_date <= window.end]
        fitted = model.fit(in_window)
        reference = reference_rate_of(in_window)
        if fitted is None or reference is None:
            continue

        governed = [
            d
            for d in ordered
            if d.day.production_date > window.end
            and (next_end is None or d.day.production_date <= next_end)
        ]
        if governed:
            episodes.extend(detect_episodes(well, governed, fitted, reference))

    # `detect_episodes` sees one governed span and cannot tell the end of its slice from the
    # end of the well's history, so it marks any episode that never recovers as open-ended.
    # Only the sweep knows which of those actually reach the end of the record. The rest ended
    # because the next reference window took over, which is not the same thing at all.
    last_valid = max(
        (d.day.production_date for d in ordered if d.day_class is DayClass.VALID_PRODUCING),
        default=None,
    )
    return [
        episode.model_copy(
            update={"open_ended": episode.open_ended and episode.offset == last_valid}
        )
        for episode in episodes
    ]
