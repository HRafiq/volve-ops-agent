"""The tools an investigation may call against production data.

Each one validates its own request, enforces the bounds in `schemas`, and returns a typed
result or a typed error. None raises on bad input, because an agent cannot act on a traceback,
and none silently truncates, because an agent that receives less than it asked for will
conclude the missing part was empty.

The domain services are the source of truth. These functions reshape and bound; they do not
compute anything the domain does not already compute. Where that line blurs is where a second
implementation of the same rule starts, and then the tool and the engine disagree.
"""

from __future__ import annotations

import collections
import datetime as dt
from collections.abc import Sequence

from pydantic import ValidationError

from volve_ops.domain.day_class import ClassifiedDay, DayClass
from volve_ops.domain.episodes import Episode
from volve_ops.domain.production_service import ProductionHistory
from volve_ops.tools.schemas import (
    MAX_DAYS_PER_REQUEST,
    MAX_EPISODES_PER_RESPONSE,
    MAX_ROWS_PER_RESPONSE,
    DataQualityView,
    DateRange,
    EpisodeView,
    ProductionDayView,
    ProductionHistoryView,
    ToolError,
    ToolErrorCode,
    ToolResult,
)

GAP_CLASSES = (DayClass.QUARANTINED, DayClass.MISSING)


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


def build_range(start: dt.date, end: dt.date) -> DateRange | ToolError:
    """Validate a date range, returning a typed error rather than raising.

    The error is distinguished by which rule failed, not by matching text in an exception
    message. An earlier version sniffed for the word "exceeds" in `str(exc)`, which made the
    code's behaviour depend on how pydantic happens to format a validation error, and which
    reported that formatting to the agent verbatim instead of the sentence the validator wrote.
    """
    if end < start:
        return ToolError(
            code=ToolErrorCode.INVALID_RANGE,
            message=f"end {end} is before start {start}",
            detail={"start": str(start), "end": str(end)},
        )
    length = (end - start).days + 1
    if length > MAX_DAYS_PER_REQUEST:
        return ToolError(
            code=ToolErrorCode.RANGE_TOO_LARGE,
            message=(
                f"a range of {length} days exceeds the {MAX_DAYS_PER_REQUEST}-day limit; "
                "ask for a shorter range rather than receiving a partial answer"
            ),
            detail={"requested_days": str(length), "limit": str(MAX_DAYS_PER_REQUEST)},
        )
    try:
        return DateRange(start=start, end=end)
    except ValidationError as exc:  # pragma: no cover - the checks above cover both rules
        return ToolError(
            code=ToolErrorCode.INVALID_RANGE,
            message="; ".join(e["msg"] for e in exc.errors()),
            detail={"start": str(start), "end": str(end)},
        )


def _well_days(
    history: ProductionHistory, well: str, window: DateRange
) -> list[ClassifiedDay] | ToolError:
    if well not in history.wells:
        return ToolError(
            code=ToolErrorCode.UNKNOWN_WELL,
            message=f"no well named {well!r} in this dataset",
            detail={"known": ", ".join(history.wells)},
        )
    days = [d for d in history.for_well(well) if window.contains(d.day.production_date)]
    if not days:
        return ToolError(
            code=ToolErrorCode.NO_DATA,
            message=f"{well} has no records between {window.start} and {window.end}",
            detail={"well": well},
        )
    return sorted(days, key=lambda d: d.day.production_date)


def get_production_history(
    history: ProductionHistory, well: str, start: dt.date, end: dt.date
) -> ToolResult[ProductionHistoryView]:
    """One well's classified daily history over a bounded range.

    The counts travel with the rows, all six classes of them, so a caller can tell a well that
    was shut in from one whose data is missing without counting day classes itself and perhaps
    counting them differently.
    """
    window = build_range(start, end)
    if isinstance(window, ToolError):
        return ToolResult(error=window)

    days = _well_days(history, well, window)
    if isinstance(days, ToolError):
        return ToolResult(error=days)

    if len(days) > MAX_ROWS_PER_RESPONSE:
        # The day bound normally binds first, because duplicate collapsing guarantees one row
        # per well-day. This is the backstop for when it did not run: a tool should not assume
        # an upstream step happened. It is a distinct code because it is an upstream fault the
        # caller cannot fix by asking for less.
        return ToolResult(
            error=ToolError(
                code=ToolErrorCode.TOO_MANY_ROWS,
                message=(
                    f"{len(days)} rows for {window.length_days} days exceeds the "
                    f"{MAX_ROWS_PER_RESPONSE}-row limit; the source was probably not "
                    "deduplicated"
                ),
                detail={"rows": str(len(days)), "days": str(window.length_days)},
            )
        )

    counts = collections.Counter(d.day_class for d in days)
    return ToolResult.succeeded(
        ProductionHistoryView(
            well=well,
            requested=window,
            days=tuple(_as_view(d) for d in days),
            valid_producing_days=counts[DayClass.VALID_PRODUCING],
            downtime_days=counts[DayClass.DOWNTIME],
            partial_days=counts[DayClass.PARTIAL],
            non_producing_days=counts[DayClass.NON_PRODUCING],
            quarantined_days=counts[DayClass.QUARANTINED],
            missing_days=counts[DayClass.MISSING],
            absent_days=window.length_days - len(days),
        )
    )


def get_data_quality(
    history: ProductionHistory, well: str, start: dt.date, end: dt.date
) -> ToolResult[DataQualityView]:
    """What a conclusion over this range would actually rest on.

    An investigation that cannot see the gaps in its own evidence will state a conclusion with
    the same confidence whether it read 300 days or 30. Two fractions, because the protocol's
    gap fraction and the question "could I conclude anything here" are not the same: a window
    of injector days has almost no gaps and no usable evidence whatsoever.
    """
    window = build_range(start, end)
    if isinstance(window, ToolError):
        return ToolResult(error=window)

    days = _well_days(history, well, window)
    if isinstance(days, ToolError):
        return ToolResult(error=days)

    valid = [d for d in days if d.day_class is DayClass.VALID_PRODUCING]
    gaps = sum(1 for d in days if d.day_class in GAP_CLASSES)
    reasons: collections.Counter[str] = collections.Counter()
    not_evaluated: set[str] = set()
    for day in days:
        reasons.update(r.value for r in day.quarantine_reasons)
        not_evaluated.update(r.value for r in day.checks_not_evaluated)

    return ToolResult.succeeded(
        DataQualityView(
            well=well,
            requested=window,
            rows_present=len(days),
            range_days=window.length_days,
            absent_days=window.length_days - len(days),
            valid_producing_days=len(valid),
            usable_fraction=len(valid) / window.length_days,
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
    if not selected:
        return ToolResult(
            error=ToolError(
                code=ToolErrorCode.NO_DATA,
                message=(f"no episodes detected for {well}" if well else "no episodes detected"),
                detail={"well": well} if well else {},
            )
        )
    if len(selected) > MAX_EPISODES_PER_RESPONSE:
        return ToolResult(
            error=ToolError(
                code=ToolErrorCode.TOO_MANY_ROWS,
                message=(
                    f"{len(selected)} episodes exceeds the "
                    f"{MAX_EPISODES_PER_RESPONSE}-episode limit; ask for one well"
                ),
                detail={"episodes": str(len(selected))},
            )
        )
    ordered = sorted(selected, key=lambda e: e.cumulative_rate_shortfall_sm3, reverse=True)
    return ToolResult.succeeded(tuple(_episode_view(e) for e in ordered))


def get_episode(episodes: Sequence[Episode], well: str, onset: dt.date) -> ToolResult[EpisodeView]:
    """One episode, addressed by the well and the day it opened."""
    for episode in episodes:
        if episode.well == well and episode.onset == onset:
            return ToolResult.succeeded(_episode_view(episode))
    return ToolResult(
        error=ToolError(
            code=ToolErrorCode.NOT_FOUND,
            message=f"no episode for {well} opening on {onset}",
            detail={"well": well, "onset": str(onset)},
        )
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
