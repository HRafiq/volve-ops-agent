"""Reading hand labels back and joining them to their events."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from volve_ops.extraction.labels import (
    LabelFileError,
    agreement,
    join_to_events,
    read_label_file,
)
from volve_ops.extraction.npt import CauseLabel, NPTEvent
from volve_ops.extraction.scoring import LabelledEvent


def event(event_id: str, comment: str = "Mud pump 1 failed.") -> NPTEvent:
    return NPTEvent(
        event_id=event_id,
        well="15/9-F-12",
        wellbore="15/9-F-12",
        source_document="d.xml",
        report_date=dt.date(2010, 6, 1),
        start_time=dt.datetime(2010, 6, 1, 4),
        end_time=dt.datetime(2010, 6, 1, 6),
        duration_hours=2.0,
        activity_code="interruption -- repair",
        category="interruption",
        subcategory="repair",
        state="ok",
        state_detail="",
        comment=comment,
    )


def label_file(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "labels.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def row(
    event_id: str = "a",
    cause: str = "equipment_failure",
    span: str | None = "pump 1 failed",
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "source_document": "d.xml",
        "activity_code": "interruption -- repair",
        "state": "ok",
        "cause": cause,
        "evidence_span": span,
        "cause_notes": None,
        "source_coding_looks_wrong": False,
        "labeller_pass": 1,
        "labelled_at": "2026-10-06T12:00:00+00:00",
    }


def test_a_well_formed_file_reads(tmp_path: Path) -> None:
    rows = read_label_file(
        label_file(tmp_path, [row("a"), row("b", cause="not_stated", span=None)])
    )
    assert [r["event_id"] for r in rows] == ["a", "b"]


def test_a_row_missing_a_required_field_is_refused(tmp_path: Path) -> None:
    bad = row()
    del bad["cause"]
    with pytest.raises(LabelFileError, match="missing"):
        read_label_file(label_file(tmp_path, [bad]))


def test_a_malformed_line_names_its_line_number(tmp_path: Path) -> None:
    path = tmp_path / "labels.jsonl"
    path.write_text(json.dumps(row()) + "\nnot json\n", encoding="utf-8")
    with pytest.raises(LabelFileError, match="line 2"):
        read_label_file(path)


def test_the_join_brings_the_comment_the_span_gate_needs(tmp_path: Path) -> None:
    """The label file does not hold the text, and the gate checks a span against the text."""
    labelled, spans = join_to_events([row("a")], [event("a")])
    assert labelled[0].comment == "Mud pump 1 failed."
    assert spans["a"] == "pump 1 failed"


def test_a_label_for_an_event_that_is_not_in_the_extraction_is_an_error(tmp_path: Path) -> None:
    """Scoring the overlap silently would report a number for a sample nobody drew."""
    with pytest.raises(LabelFileError, match="drifted apart"):
        join_to_events([row("ghost")], [event("a")])


def test_an_unknown_cause_is_refused(tmp_path: Path) -> None:
    with pytest.raises(LabelFileError, match="not a cause label"):
        join_to_events([row("a", cause="vibes")], [event("a")])


def test_agreement_is_computed_over_the_overlap() -> None:
    first = [
        LabelledEvent(event_id="a", cause=CauseLabel.EQUIPMENT_FAILURE),
        LabelledEvent(event_id="b", cause=CauseLabel.NOT_STATED),
        LabelledEvent(event_id="c", cause=CauseLabel.HOLE_PROBLEM),
    ]
    second = [
        LabelledEvent(event_id="a", cause=CauseLabel.EQUIPMENT_FAILURE),
        LabelledEvent(event_id="b", cause=CauseLabel.RIG_SERVICE),
    ]
    assert agreement(first, second) == (1, 2)
