"""Quarantine records."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from volve_ops import INGEST_VERSION
from volve_ops.ingest.quarantine import QuarantineReason, QuarantineRecord, UnsafeInputError


def test_a_record_carries_enough_context_to_find_the_input_again() -> None:
    record = QuarantineRecord(
        reason=QuarantineReason.HOURS_OUT_OF_RANGE,
        detail="on_stream_hours=30.0",
        source="production.daily",
        well="15/9-F-1",
        production_date=dt.date(2010, 6, 1),
    )
    assert record.reason is QuarantineReason.HOURS_OUT_OF_RANGE
    assert record.parser_version == INGEST_VERSION


def test_records_are_frozen_and_reject_unknown_fields() -> None:
    record = QuarantineRecord(
        reason=QuarantineReason.MALFORMED_INPUT, detail="bad xml", source="f.xml"
    )
    with pytest.raises(ValidationError):
        record.detail = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        QuarantineRecord.model_validate(
            {
                "reason": QuarantineReason.MALFORMED_INPUT,
                "detail": "d",
                "source": "s",
                "unexpected": "x",
            }
        )


def test_reason_values_are_stable_strings_because_they_are_persisted() -> None:
    assert QuarantineReason.NO_FLUIDS_ON_PRODUCING_DAY.value == "no_fluids_on_producing_day"
    assert QuarantineReason.DUPLICATE_DISAGREEMENT.value == "duplicate_disagreement"


def test_unsafe_input_error_is_an_exception_not_a_return_value() -> None:
    """A hostile file is never a reason to relax validation, so there is no permissive path."""
    assert issubclass(UnsafeInputError, Exception)
