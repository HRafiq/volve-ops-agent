"""Canonical production records and the physical checks that gate them.

This module holds the project's own schema, not the source's. Mapping source columns onto
it is a separate step that needs the data; everything here is fixed in advance.

Three rules carry most of the weight:

Missing is not zero. Every optional quantity stays None when the source has no value, and
nothing anywhere substitutes a zero for it. A zero on-stream-hour day and a day nobody
recorded look nothing alike operationally, and collapsing them is how downtime turns into
underperformance. Non-finite floats are rejected for the same reason: a spreadsheet reader
represents a blank numeric cell as NaN, and a NaN that reached these fields would be neither
missing nor quarantined, would fail every physical check, and would propagate silently
through every later sum.

Nothing numeric is parsed from text. The model is strict, so a float field will not accept
the string "5.0" and an unexpected column is an error rather than something dropped on the
floor. A silent conversion at ingest is a wrong number everywhere downstream with no trace of
where it came from. Pydantic does still widen an int to a float, which is safe for values a
daily production record holds.

A check that cannot run is reported, not skipped. docs/eval_protocol.md section 7 requires
that a dropped check be disclosed wherever affected results appear, so the check function
returns what it could not evaluate alongside what failed.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from enum import StrEnum
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field

from volve_ops import INGEST_VERSION
from volve_ops.ingest.quarantine import QuarantineReason

# Rejects NaN and Inf while still accepting an ordinary float. StrictFloat alone does not.
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class WellStatus(StrEnum):
    """Canonical well status.

    Source vocabularies map onto these before a record is built, never the reverse. The
    model is strict, so a raw source string is rejected rather than guessed at, including
    one that happens to spell a member name.
    """

    PRODUCING = "producing"
    SHUT_IN = "shut_in"
    INJECTING = "injecting"
    TESTING = "testing"
    OTHER = "other"


class ProductionDay(BaseModel):
    """One well-day as the project stores it, in canonical units.

    Volumes are Sm3 and on-stream time is hours, converted at the boundary by
    volve_ops.ingest.units. Optional fields are None when the source had no value.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    well: str
    production_date: dt.date

    on_stream_hours: FiniteFloat | None = None
    oil_volume_sm3: FiniteFloat | None = None
    gas_volume_sm3: FiniteFloat | None = None
    water_volume_sm3: FiniteFloat | None = None

    well_status: WellStatus | None = None
    choke_size: FiniteFloat | None = None
    choke_unit: str | None = None

    source: str
    parser_version: str = INGEST_VERSION


class CapacityLimits(BaseModel):
    """Per-fluid absolute implausibility bounds, in Sm3 per day.

    Separate per fluid because daily oil and gas volumes in Sm3 differ by around three
    orders of magnitude; one shared scalar set from an oil figure would quarantine every
    producing day on its gas.

    docs/eval_protocol.md section 7 defers these values to a published field or facility
    capacity figure, so this object does not exist until that figure does.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    oil_sm3: FiniteFloat | None = None
    gas_sm3: FiniteFloat | None = None
    water_sm3: FiniteFloat | None = None


# Columns whose disagreement between duplicate rows makes a day unusable. A disagreement in
# a column this project never reads is not a reason to discard a day.
#
# choke_unit is included because a choke setting is a magnitude together with its unit:
# 30 mm and 30 percent describe different wells, and collapsing them would resolve a real
# configuration conflict by whichever row happened to be read first.
MATERIAL_FIELDS: Final[tuple[str, ...]] = (
    "on_stream_hours",
    "oil_volume_sm3",
    "gas_volume_sm3",
    "water_volume_sm3",
    "well_status",
    "choke_size",
    "choke_unit",
)


class CheckOutcome(BaseModel):
    """What the physical checks found, and what they could not evaluate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    failures: tuple[QuarantineReason, ...] = ()
    not_evaluated: tuple[QuarantineReason, ...] = ()

    @property
    def quarantined(self) -> bool:
        return bool(self.failures)


def physical_checks(
    day: ProductionDay,
    *,
    capacity: CapacityLimits | None,
    gas_and_water_columns_present: bool,
) -> CheckOutcome:
    """Apply the pre-registered physical checks from docs/eval_protocol.md section 7.

    None of them looks at a model, a prediction or a residual, and none may be extended to
    do so: a quarantine rule that can see how a model performed is a rule that can be used
    to hide how a model performed.

    Both keyword arguments are required rather than defaulted, so that a caller cannot
    disable a pre-registered check by forgetting it exists.

    capacity is None until a published capacity figure exists. gas_and_water_columns_present
    says whether the source carries those columns at all; when it does not, the no-fluids
    check cannot run and is returned under not_evaluated for disclosure.
    """
    failures: list[QuarantineReason] = []
    not_evaluated: list[QuarantineReason] = []
    hours = day.on_stream_hours

    if hours is not None and (hours < 0.0 or hours > 24.0):
        failures.append(QuarantineReason.HOURS_OUT_OF_RANGE)

    volumes = (day.oil_volume_sm3, day.gas_volume_sm3, day.water_volume_sm3)
    if any(v is not None and v < 0.0 for v in volumes):
        failures.append(QuarantineReason.NEGATIVE_VOLUME)

    # Section 7 names a nonzero oil volume on a zero-hour day, which includes a negative one.
    if hours == 0.0 and day.oil_volume_sm3 is not None and day.oil_volume_sm3 != 0.0:
        failures.append(QuarantineReason.VOLUME_WITHOUT_HOURS)

    # Zero oil on a producing day that nothing corroborates. An absent gas or water value is
    # absence of corroboration, exactly like a zero: the point of the check is that a
    # recording gap is the likelier reading, and a null is what a recording gap looks like.
    #
    # The status qualifier matters. Without it an injection day with no produced fluids would
    # be quarantined instead of classed non-producing, inflating every injector's quarantine
    # fraction.
    if not gas_and_water_columns_present:
        not_evaluated.append(QuarantineReason.NO_FLUIDS_ON_PRODUCING_DAY)
    elif (
        day.well_status is WellStatus.PRODUCING
        and hours is not None
        and hours > 0.0
        and day.oil_volume_sm3 == 0.0
        and not day.gas_volume_sm3
        and not day.water_volume_sm3
    ):
        failures.append(QuarantineReason.NO_FLUIDS_ON_PRODUCING_DAY)

    if capacity is None:
        not_evaluated.append(QuarantineReason.VOLUME_ABOVE_CAPACITY)
    else:
        pairs = (
            (day.oil_volume_sm3, capacity.oil_sm3),
            (day.gas_volume_sm3, capacity.gas_sm3),
            (day.water_volume_sm3, capacity.water_sm3),
        )
        if any(v is not None and limit is not None and v > limit for v, limit in pairs):
            failures.append(QuarantineReason.VOLUME_ABOVE_CAPACITY)

    return CheckOutcome(failures=tuple(failures), not_evaluated=tuple(not_evaluated))


class DuplicateConflict(BaseModel):
    """A set of duplicate well-days that disagree, and the fields they disagree on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rows: tuple[ProductionDay, ...]
    disagreeing_fields: tuple[str, ...]
    reason: QuarantineReason = QuarantineReason.DUPLICATE_DISAGREEMENT


def collapse_duplicates(
    days: Iterable[ProductionDay],
) -> tuple[list[ProductionDay], list[DuplicateConflict]]:
    """Collapse duplicate well-days that agree, and quarantine those that do not.

    Agreement is judged on MATERIAL_FIELDS only, and by exact equality. Exact equality is
    deliberate but it is a free parameter: once a source path converts units before
    comparison, two reports of the same volume can differ in the last bits and a good day
    would be discarded. A comparison tolerance is a threshold under docs/eval_protocol.md
    section 3, so it cannot be invented here. Until a protocol version sets one, equality
    stays exact and this comment is the record of the choice.

    Where duplicates agree, the surviving row is the one whose source sorts first, so the
    provenance recorded for a day does not depend on the order files happened to be read in.

    Returns the surviving days and the conflicts, so a caller records both rather than
    discovering later that rows went missing. Note that one row carrying a value where its
    duplicate carries None counts as disagreement and quarantines the day; that will discard
    usable days where the same date appears in two sources with different column coverage,
    and section 7 is what requires it.
    """
    grouped: dict[tuple[str, dt.date], list[ProductionDay]] = {}
    for day in days:
        grouped.setdefault((day.well, day.production_date), []).append(day)

    kept: list[ProductionDay] = []
    conflicts: list[DuplicateConflict] = []

    for rows in grouped.values():
        if len(rows) == 1:
            kept.append(rows[0])
            continue

        disagreeing = tuple(
            name for name in MATERIAL_FIELDS if len({getattr(row, name) for row in rows}) > 1
        )
        if disagreeing:
            conflicts.append(
                DuplicateConflict(
                    rows=tuple(sorted(rows, key=lambda r: r.source)),
                    disagreeing_fields=disagreeing,
                )
            )
        else:
            kept.append(min(rows, key=lambda r: r.source))

    kept.sort(key=lambda d: (d.well, d.production_date))
    return kept, conflicts
