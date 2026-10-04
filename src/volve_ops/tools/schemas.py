"""Request and response types, and the limits every tool enforces.

An agent's input is untrusted. Not because the model is adversarial, but because a model asked
to investigate a well will cheerfully request ten years of daily data for every well at once,
and because text inside a drilling report can try to widen a request beyond what the
investigation needs. The bounds here are what stop either from mattering.

Every tool returns a typed result or a typed error. A tool that raises leaves an agent to
interpret a traceback, and a tool that returns a bare string invites the model to parse prose.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Bounds. A request outside them is refused rather than truncated: silently returning less than
# was asked for is how an agent concludes a well had no production in a period it never saw.
MAX_DAYS_PER_REQUEST = 1100
MAX_ROWS_PER_RESPONSE = 1200
MAX_WELLS_PER_REQUEST = 10


class ToolErrorCode(StrEnum):
    """Stable error codes. An agent branches on these, not on message text."""

    UNKNOWN_WELL = "unknown_well"
    RANGE_TOO_LARGE = "range_too_large"
    INVALID_RANGE = "invalid_range"
    TOO_MANY_WELLS = "too_many_wells"
    NO_DATA = "no_data"
    NOT_FOUND = "not_found"


class ToolError(BaseModel):
    """A refusal an agent can act on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ToolErrorCode
    message: str
    detail: dict[str, str] = Field(default_factory=dict)


T = TypeVar("T")


class ToolResult(BaseModel, Generic[T]):
    """Either a value or an error, never both, and never an exception."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: T | None = None
    error: ToolError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @model_validator(mode="after")
    def _exactly_one(self) -> ToolResult[T]:
        if (self.value is None) == (self.error is None):
            raise ValueError("a tool result carries exactly one of value or error")
        return self

    @classmethod
    def failed(cls, code: ToolErrorCode, message: str, **detail: str) -> ToolResult[T]:
        return cls(error=ToolError(code=code, message=message, detail=detail))

    @classmethod
    def succeeded(cls, value: T) -> ToolResult[T]:
        return cls(value=value)


class DateRange(BaseModel):
    """A bounded, validated date range. Every query-shaped tool takes one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: dt.date
    end: dt.date

    @model_validator(mode="after")
    def _within_bounds(self) -> DateRange:
        if self.end < self.start:
            raise ValueError(f"end {self.end} is before start {self.start}")
        if (self.end - self.start).days + 1 > MAX_DAYS_PER_REQUEST:
            raise ValueError(
                f"range of {(self.end - self.start).days + 1} days exceeds the "
                f"{MAX_DAYS_PER_REQUEST}-day limit"
            )
        return self

    def contains(self, day: dt.date) -> bool:
        return self.start <= day <= self.end


class ProductionDayView(BaseModel):
    """One well-day as a tool reports it.

    A flattened, explicit view rather than the internal record. An agent should not have to
    know that a rate is defined only on one day class; the view says so by carrying None and
    naming the class.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    date: dt.date
    day_class: str
    on_stream_hours: float | None
    oil_volume_sm3: float | None
    normalised_rate_sm3_per_day: float | None
    choke_size: float | None
    quarantine_reasons: tuple[str, ...] = ()


class ProductionHistoryView(BaseModel):
    """A well's history over a requested range, with what was excluded and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    well: str
    requested: DateRange
    days: tuple[ProductionDayView, ...]
    valid_producing_days: int
    downtime_days: int
    partial_days: int
    quarantined_days: int
    missing_days: int
    truncated: bool = False


class DataQualityView(BaseModel):
    """What a conclusion drawn over this range would rest on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    well: str
    requested: DateRange
    total_days: int
    valid_producing_days: int
    gap_fraction: float
    quarantine_reasons: dict[str, int]
    checks_not_evaluated: tuple[str, ...]
    first_valid_day: dt.date | None
    last_valid_day: dt.date | None


class EpisodeView(BaseModel):
    """A detected episode as a tool reports it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    well: str
    onset: dt.date
    offset: dt.date
    valid_producing_days: int
    cumulative_rate_shortfall_sm3: float
    deferred_volume_sm3: float
    shortfall_threshold_sm3: float
    reference_rate_sm3_per_day: float
    gap_fraction: float
    open_ended: bool
    poorly_evidenced: bool
