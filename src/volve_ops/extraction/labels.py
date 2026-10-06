"""Reading hand labels back, and joining them to the events they describe.

The labelling tool writes JSON lines; the scoring harness wants `LabelledEvent` objects
carrying the comment, because the span gate checks a cited span against the text it cites and
the label file does not hold the text. This module is that join, in one place, so a scoring run
cannot quietly use a different one.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from volve_ops.extraction.npt import CauseLabel, NPTEvent
from volve_ops.extraction.scoring import LabelledEvent, LabelSource


class LabelFileError(Exception):
    """The label file does not say what the labelling guide requires."""


# `label_source` is required rather than defaulted. Protocol section 17.2 suspends two pass
# marks on its value, so a row that omits it is a row whose provenance would be guessed.
REQUIRED_FIELDS = ("event_id", "cause", "labeller_pass", "label_source")


def read_label_file(path: Path) -> list[dict[str, object]]:
    """Read the raw rows, refusing a file that is missing what the guide fixes."""
    rows: list[dict[str, object]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LabelFileError(f"{path.name} line {number}: not JSON: {exc}") from exc
        missing = [f for f in REQUIRED_FIELDS if f not in row]
        if missing:
            raise LabelFileError(f"{path.name} line {number}: missing {missing}")
        rows.append(row)
    return rows


def join_to_events(
    rows: Sequence[Mapping[str, object]], events: Iterable[NPTEvent]
) -> tuple[list[LabelledEvent], dict[str, str | None]]:
    """Pair labels with their events, returning the labelled set and the cited spans.

    A label whose event is not in the store is an error rather than a skipped row: it means the
    labels and the extraction have drifted apart, and silently scoring the overlap would report
    a number for a sample nobody drew.
    """
    by_id = {e.event_id: e for e in events}
    labelled: list[LabelledEvent] = []
    spans: dict[str, str | None] = {}

    for row in rows:
        event_id = str(row["event_id"])
        event = by_id.get(event_id)
        if event is None:
            raise LabelFileError(
                f"label refers to {event_id}, which is not in this extraction; "
                "the labels and the store have drifted apart"
            )
        try:
            cause = CauseLabel(str(row["cause"]))
        except ValueError as exc:
            raise LabelFileError(f"{event_id}: {row['cause']!r} is not a cause label") from exc

        if "label_source" not in row:
            raise LabelFileError(
                f"{event_id}: no label_source. Protocol section 17.2 suspends two pass marks on "
                "this field, so it is required rather than assumed"
            )
        try:
            source = LabelSource(str(row["label_source"]))
        except ValueError as exc:
            raise LabelFileError(
                f"{event_id}: {row['label_source']!r} is not a label source; "
                f"expected one of {[s.value for s in LabelSource]}"
            ) from exc

        raw_span = row.get("evidence_span")
        span = None if raw_span is None else str(raw_span)
        if cause is CauseLabel.NOT_STATED and span is not None:
            raise LabelFileError(
                f"{event_id}: cause is not_stated but a span is cited. The guide defines "
                "not_stated as the absence of a supporting substring, so the two cannot coexist"
            )
        if cause is not CauseLabel.NOT_STATED and span is None:
            raise LabelFileError(
                f"{event_id}: cause {cause.value} carries no span. A cause without a span is "
                "the thing the labelling guide exists to prevent"
            )
        if span is not None and span not in event.comment:
            raise LabelFileError(
                f"{event_id}: the cited span is not a substring of the comment it cites"
            )

        labelled.append(
            LabelledEvent(
                event_id=event_id,
                cause=cause,
                label_source=source,
                evidence_span=span,
                comment=event.comment,
            )
        )
        spans[event_id] = span

    return labelled, spans


def agreement(first: Sequence[LabelledEvent], second: Sequence[LabelledEvent]) -> tuple[int, int]:
    """How often two labelling passes agree, over the events both cover.

    The guide reports this as the ceiling on what agreement with a system could mean, so it is
    computed over the overlap rather than over either pass alone.
    """
    one = {e.event_id: e.cause for e in first}
    two = {e.event_id: e.cause for e in second}
    shared = sorted(set(one) & set(two))
    return sum(1 for i in shared if one[i] is two[i]), len(shared)
