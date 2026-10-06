"""Non-productive time events, extracted deterministically from drilling reports.

docs/eval_protocol.md section 14 is the specification. The parts that need no judgement are
computed here and never go near a model: whether a block is non-productive, how long it lasted,
and what the source filed it under. A model asked to classify what is already classified can
only introduce error, and the error would be invisible because it would look like extraction.

What is left for a model is the one question the structured fields cannot answer: given an
event the source has already categorised and timed, what does the narrative say caused it.
This module leaves those fields empty and marks the event as awaiting attribution.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Final
from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict, Field

from volve_ops import INGEST_VERSION
from volve_ops.domain.well_naming import canonical_from_ddr_token, well_of
from volve_ops.extraction import EXTRACTOR_VERSION
from volve_ops.ingest.quarantine import UnsafeInputError
from volve_ops.ingest.safe_xml import parse_xml_file

WITSML_NS: Final[str] = "{http://www.witsml.org/schemas/1series}"

# Section 14.1. A block is non-productive if its activity code begins `interruption`, or its
# state is `fail`. The two do not coincide: 96 fail-state blocks in this corpus sit under a
# different head, mostly failed casing runs and drilling, and a failed casing run is lost time
# whatever it was filed under.
INTERRUPTION_HEAD: Final[str] = "interruption"
FAIL_STATE: Final[str] = "fail"


class CauseLabel(StrEnum):
    """The cause taxonomy, fixed in docs/labelling_guide.md before any label was made."""

    EQUIPMENT_FAILURE = "equipment_failure"
    EQUIPMENT_MAINTENANCE = "equipment_maintenance"
    HOLE_PROBLEM = "hole_problem"
    CEMENTING_PROBLEM = "cementing_problem"
    WAITING_ON_WEATHER = "waiting_on_weather"
    WAITING_ON_LOGISTICS = "waiting_on_logistics"
    WAITING_ON_CEMENT = "waiting_on_cement"
    RIG_SERVICE = "rig_service"
    WELL_CONTROL = "well_control"
    HUMAN_OR_PROCEDURAL = "human_or_procedural"
    OTHER = "other"
    NOT_STATED = "not_stated"


class NPTEvent(BaseModel):
    """One non-productive event. Everything here except the cause is from the source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    well: str
    wellbore: str
    source_document: str
    report_date: dt.date

    start_time: dt.datetime
    end_time: dt.datetime
    duration_hours: float

    activity_code: str
    category: str
    subcategory: str
    state: str
    state_detail: str
    comment: str

    # Left for the attribution step. An event with no cause is not a failure of extraction;
    # a great many comments say what was done and not why, and inventing a cause for those is
    # the specific failure this project exists to prevent.
    cause: CauseLabel | None = None
    evidence_span: str | None = None
    equipment: str | None = None
    attribution_confidence: float | None = None

    needs_review: bool = False
    review_reasons: tuple[str, ...] = Field(default_factory=tuple)

    parser_version: str = INGEST_VERSION
    extractor_version: str = EXTRACTOR_VERSION

    @property
    def has_attribution(self) -> bool:
        return self.cause is not None


def _text(element: Element, tag: str) -> str:
    found = element.find(f"{WITSML_NS}{tag}")
    return (found.text or "").strip() if found is not None and found.text else ""


def _parse_timestamp(raw: str) -> dt.datetime | None:
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw)
    except ValueError:
        return None


def _event_id(source: str, start: dt.datetime, code: str, index: int) -> str:
    """A stable id, derived from what the event is rather than from when it was extracted.

    Re-running extraction on unchanged input must produce the same ids, or every downstream
    reference breaks on a re-run and a correction cannot be tied to the event it corrected.
    """
    digest = hashlib.sha256(f"{source}|{start.isoformat()}|{code}|{index}".encode()).hexdigest()
    return f"npt_{digest[:16]}"


def is_non_productive(code: str, state: str) -> bool:
    """Section 14.1's rule, in one place so nothing can apply a narrower version of it."""
    head = code.split("--")[0].strip().lower()
    return head == INTERRUPTION_HEAD or state.strip().lower() == FAIL_STATE


def extract_from_report(path: Path) -> Iterator[NPTEvent]:
    """Every non-productive event in one drilling report.

    Parsing goes through the hardened reader, so a report with an external entity or a
    recursive definition is refused rather than read.
    """
    root = parse_xml_file(path)

    token, report_date = parse_report_filename(path)
    wellbore = canonical_from_ddr_token(token)

    for report in root.iter(f"{WITSML_NS}drillReport"):
        for index, activity in enumerate(report.iter(f"{WITSML_NS}activity")):
            code = _text(activity, "proprietaryCode")
            state = _text(activity, "state")
            if not is_non_productive(code, state):
                continue

            start = _parse_timestamp(_text(activity, "dTimStart"))
            end = _parse_timestamp(_text(activity, "dTimEnd"))
            if start is None or end is None:
                # Section 14.3 requires every block meeting the 14.1 rule to become exactly one
                # event, so a qualifying block that cannot be timed is a parser defect and is
                # raised rather than skipped. Dropping it silently would make the exactness
                # pass mark pass by losing the evidence against it.
                raise UnsafeInputError(
                    f"{path.name}: a non-productive block has no usable timestamps "
                    f"({_text(activity, 'dTimStart')!r} to {_text(activity, 'dTimEnd')!r})"
                )

            duration = (end - start).total_seconds() / 3600.0
            reasons: list[str] = []
            if duration < 0:
                reasons.append("negative_duration")
            comment = _text(activity, "comments")
            if not comment:
                reasons.append("no_comment")

            head, _, tail = code.partition("--")
            yield NPTEvent(
                event_id=_event_id(path.name, start, code, index),
                well=well_of(wellbore),
                wellbore=wellbore,
                source_document=path.name,
                report_date=report_date,
                start_time=start,
                end_time=end,
                duration_hours=duration,
                activity_code=code,
                category=head.strip(),
                subcategory=tail.strip(),
                state=state,
                state_detail=_text(activity, "stateDetailActivity"),
                comment=comment,
                needs_review=bool(reasons),
                review_reasons=tuple(reasons),
            )


_REPORT_FILENAME = re.compile(r"^(?P<token>.+)_(?P<y>\d{4})_(?P<m>\d{2})_(?P<d>\d{2})$")


def parse_report_filename(path: Path) -> tuple[str, dt.date]:
    """Split a drilling-report filename into its well token and its date.

    Done in one place and before anything else, so a malformed name fails as a refused input
    rather than as whatever the next step happens to raise. Stripping the date by counting
    characters, as an earlier version did, breaks on any filename that is not exactly the shape
    expected and fails somewhere unhelpful when it does.
    """
    match = _REPORT_FILENAME.match(path.stem)
    if not match:
        raise UnsafeInputError(f"no date in drilling-report filename: {path.name}")
    try:
        day = dt.date(int(match["y"]), int(match["m"]), int(match["d"]))
    except ValueError as exc:
        raise UnsafeInputError(f"bad date in drilling-report filename: {path.name}") from exc
    return match["token"], day


def extract_from_directory(report_dir: Path) -> list[NPTEvent]:
    """Every non-productive event across a corpus of reports, in document order."""
    events: list[NPTEvent] = []
    for path in sorted(report_dir.glob("*.xml")):
        events.extend(extract_from_report(path))
    return events
