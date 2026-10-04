"""Quarantine reasons and records.

A quarantined input is never silently dropped and never repaired. It is set aside with
a reason, and the quarantined fraction is reported next to any result that depends on
the data it came from, because a result computed on 70 percent of a well's days means
something different from one computed on all of them.

The first six reasons are the physical checks pre-registered in docs/eval_protocol.md
section 7. The last two are input-level outcomes rather than day-level checks: a file that
could not be read, and a file that was refused as unsafe.

No reason may reference a model residual, a prediction or a detector output, in this version
or any later one: a quarantine rule that can see how a model performed is a rule that can be
used to hide how a model performed.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from volve_ops import INGEST_VERSION


class QuarantineReason(StrEnum):
    """Why a record was set aside. Values are stable; they appear in stored records."""

    HOURS_OUT_OF_RANGE = "hours_out_of_range"
    NEGATIVE_VOLUME = "negative_volume"
    VOLUME_WITHOUT_HOURS = "volume_without_hours"
    NO_FLUIDS_ON_PRODUCING_DAY = "no_fluids_on_producing_day"
    DUPLICATE_DISAGREEMENT = "duplicate_disagreement"
    VOLUME_ABOVE_CAPACITY = "volume_above_capacity"

    # Not a day-level physical check: the input could not be read or validated at all.
    MALFORMED_INPUT = "malformed_input"
    UNSAFE_INPUT = "unsafe_input"


class QuarantineRecord(BaseModel):
    """One quarantined input, with enough context to find it again."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: QuarantineReason
    detail: str
    source: str
    well: str | None = None
    production_date: dt.date | None = None
    parser_version: str = INGEST_VERSION


class UnsafeInputError(Exception):
    """An input was rejected because processing it would be unsafe.

    Raised rather than returned. A malformed or hostile file is never a reason to relax
    validation, so there is no permissive path a caller can opt into.
    """
