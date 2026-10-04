"""The tools an investigation may call against production data.

Each one validates its own request, enforces the bounds in `schemas`, and returns a typed
result or a typed error. None of them raises on bad input, because an agent cannot act on a
traceback, and none of them silently truncates, because an agent that receives less than it
asked for will conclude the missing part was empty.

The domain services are the source of truth. These functions reshape and bound; they do not
compute anything the domain does not already compute. Where that line blurs is where a second
implementation of the same rule starts, and then the tool and the engine disagree.
"""

from __future__ import annotations

import collections
import datetime as dt
from collections.abc import Sequence

from volve_ops.domain.day_class import ClassifiedDay, DayClass
from volve_ops.domain.episodes import Episode
from volve_ops.domain.production_service import ProductionHistory
from volve_ops.tools.schemas import (
    MAX_ROWS_PER_RESPONSE,
    DataQualityView,
    DateRange,
    EpisodeView,
    ProductionDayView,
    ProductionHistoryView,
    ToolErrorCode,
    ToolResult,
)


def _as_view(day: ClassifiedDay) -> ProductionDayView:
    return ProductionDayView(
        date=day.day.production_date,
        day_class=day.day_class.value,
        on_stream_hours=day.day.on_stream_hours,
        oil_volume_sm3=day.day.oil_volume_sm3,
        normalised_rate_sm3_per_day=day.q_24h,
        choke_size=day.day.choke_size,
        quarantine_reasons=tuple(r.value for r in day.quarantine_reasons),
    )


def _well_days(
    history: ProductionHistory, well: str, window: DateRange
) -> list[ClassifiedDay] | ToolResult[None]:
    if well not in history.wells:
        return ToolResult.failed(
            ToolErrorCode.UNKNOWN_WELL,
            f"no well named {well!r} in this dataset",
            known=", ".join(history.wells),
        )
    days = [d for d in history.for_well(well) if window.contains(d.day.production_date)]
    if not days:
        return ToolResult.failed(
            ToolErrorCode.NO_DATA,
            f"{well} has no records between {window.start} and {window.end}",
            well=well,
        )
    return sorted(days, key=lambda d: d.day.production_date)


def get_production_history(
    history: ProductionHistory, well: str, start: dt.date, end: dt.date
) -> ToolResult[ProductionHistoryView]:
    """One well's classified daily history over a bounded range.

    The counts travel with the rows so that a caller reading a short history can tell a well
    that was shut in from one whose data is missing, without having to count day classes itself
    and perhaps count them differently.
    """
    try:
        window = DateRange(start=start, end=end)
    except ValueError as exc:
        code = (
            ToolErrorCode.RANGE_TOO_LARGE if "exceeds" in str(exc) else ToolErrorCode.INVALID_RANGE
        )
        return ToolResult.failed(code, str(exc), start=str(start), end=str(end))

    days = _well_days(history, well, window)
    if isinstance(days, ToolResult):
        return ToolResult.failed(
            days.error.code if days.error else ToolErrorCode.NO_DATA,
            days.error.message if days.error else "no data",
            **(days.error.detail if days.error else {}),
        )

    counts = collections.Counter(d.day_class for d in days)
    # The day bound normally binds first, because duplicate collapsing guarantees one row per
    # well-day. This is the backstop for when it did not run: a tool should not assume an
    # upstream step happened, and returning thousands of rows because a source had duplicates
    # is a worse failure than refusing.
    if len(days) > MAX_ROWS_PER_RESPONSE:
        return ToolResult.failed(
            ToolErrorCode.RANGE_TOO_LARGE,
            f"{len(days)} rows exceeds the {MAX_ROWS_PER_RESPONSE}-row limit; "
            "ask for a shorter range rather than receiving a partial answer",
            rows=str(len(days)),
        )

    return ToolResult.succeeded(
        ProductionHistoryView(
            well=well,
            requested=window,
            days=tuple(_as_view(d) for d in days),
            valid_producing_days=counts[DayClass.VALID_PRODUCING],
            downtime_days=counts[DayClass.DOWNTIME],
            partial_days=counts[DayClass.PARTIAL],
            quarantined_days=counts[DayClass.QUARANTINED],
            missing_days=counts[DayClass.MISSING],
        )
    )


def get_data_quality(
    history: ProductionHistory, well: str, start: dt.date, end: dt.date
) -> ToolResult[DataQualityView]:
    """What a conclusion over this range would actually rest on.

    An investigation that cannot see the gaps in its own evidence will state a conclusion with
    the same confidence whether it read 300 days or 30. This is the tool that makes the
    difference visible, and the protocol requires the gap fraction to be reported beside any
    result that depends on it.
    """
    try:
        window = DateRange(start=start, end=end)
    except ValueError as exc:
        code = (
            ToolErrorCode.RANGE_TOO_LARGE if "exceeds" in str(exc) else ToolErrorCode.INVALID_RANGE
        )
        return ToolResult.failed(code, str(exc), start=str(start), end=str(end))

    days = _well_days(history, well, window)
    if isinstance(days, ToolResult):
        return ToolResult.failed(
            days.error.code if days.error else ToolErrorCode.NO_DATA,
            days.error.message if days.error else "no data",
            **(days.error.detail if days.error else {}),
        )

    valid = [d for d in days if d.day_class is DayClass.VALID_PRODUCING]
    gaps = sum(1 for d in days if d.day_class in (DayClass.QUARANTINED, DayClass.MISSING))
    reasons: collections.Counter[str] = collections.Counter()
    not_evaluated: set[str] = set()
    for day in days:
        reasons.update(r.value for r in day.quarantine_reasons)
        not_evaluated.update(r.value for r in day.checks_not_evaluated)

    return ToolResult.succeeded(
        DataQualityView(
            well=well,
            requested=window,
            total_days=len(days),
            valid_producing_days=len(valid),
            gap_fraction=gaps / len(days),
            quarantine_reasons=dict(reasons),
            checks_not_evaluated=tuple(sorted(not_evaluated)),
            first_valid_day=valid[0].day.production_date if valid else None,
            last_valid_day=valid[-1].day.production_date if valid else None,
        )
    )


def list_episodes(
    episodes: Sequence[Episode], well: str | None = None
) -> ToolResult[tuple[EpisodeView, ...]]:
    """Detected episodes, optionally for one well, most costly first."""
    selected = [e for e in episodes if well is None or e.well == well]
    if well is not None and not selected:
        return ToolResult.failed(
            ToolErrorCode.NO_DATA, f"no episodes detected for {well}", well=well
        )
    ordered = sorted(selected, key=lambda e: e.cumulative_rate_shortfall_sm3, reverse=True)
    return ToolResult.succeeded(tuple(_episode_view(e) for e in ordered))


def get_episode(episodes: Sequence[Episode], well: str, onset: dt.date) -> ToolResult[EpisodeView]:
    """One episode, addressed by the well and the day it opened."""
    for episode in episodes:
        if episode.well == well and episode.onset == onset:
            return ToolResult.succeeded(_episode_view(episode))
    return ToolResult.failed(
        ToolErrorCode.NOT_FOUND,
        f"no episode for {well} opening on {onset}",
        well=well,
        onset=str(onset),
    )


def _episode_view(episode: Episode) -> EpisodeView:
    return EpisodeView(
        well=episode.well,
        onset=episode.onset,
        offset=episode.offset,
        valid_producing_days=episode.valid_producing_days,
        cumulative_rate_shortfall_sm3=episode.cumulative_rate_shortfall_sm3,
        deferred_volume_sm3=episode.deferred_volume_sm3,
        shortfall_threshold_sm3=episode.shortfall_threshold_sm3,
        reference_rate_sm3_per_day=episode.reference_rate_sm3_per_day,
        gap_fraction=episode.gap_fraction,
        open_ended=episode.open_ended,
        poorly_evidenced=episode.poorly_evidenced,
    )
