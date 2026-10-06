"""Section 14.3's two pass marks: event detection is exact, and duration is exact.

Both are checks of the parser against the source XML, which is why protocol section 17 leaves
them gating while it suspends the cause-attribution marks. Nothing here reads a cause.

The walk below is deliberately not `extract_from_report`. Re-running the extractor and comparing
its output with itself would pass by construction. What is shared with the extractor is exactly
one thing, `is_non_productive`, because section 14.1's rule is the specification and a second
copy of it would test the copy. Everything else, finding the blocks, counting them, reading the
timestamps and pairing them with events, is independent here, so a dropped block, a duplicated
one, an id collision or a duration taken from the wrong fields shows up as a mismatch.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Final
from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from volve_ops.extraction.npt import WITSML_NS, NPTEvent, is_non_productive
from volve_ops.ingest.safe_xml import parse_xml_file

# Section 14.3.2 allows one minute, which is arithmetic tolerance rather than a judgement.
DURATION_TOLERANCE_HOURS: Final[float] = 1.0 / 60.0


class IntegrityFinding(BaseModel):
    """One disagreement between the source and the extracted events."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    source_document: str
    detail: str


class IntegrityReport(BaseModel):
    """What the two section 14.3 pass marks measured."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    documents: int
    qualifying_blocks: int
    events_checked: int
    durations_checked: int
    findings: tuple[IntegrityFinding, ...]

    @property
    def detection_exact(self) -> bool:
        """Pass mark 1. Every qualifying block became exactly one event, and nothing else did."""
        return self.qualifying_blocks == self.events_checked and not any(
            f.kind in {"missing_event", "unexpected_event", "duplicate_event_id"}
            for f in self.findings
        )

    @property
    def duration_exact(self) -> bool:
        """Pass mark 2. Every duration matches the block's own timestamps."""
        return not any(f.kind == "duration_mismatch" for f in self.findings)

    @property
    def passed(self) -> bool:
        return self.detection_exact and self.duration_exact


def _text(element: Element, tag: str) -> str:
    found = element.find(f"{WITSML_NS}{tag}")
    return (found.text or "").strip() if found is not None and found.text else ""


def _timestamp(raw: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def check_reports(paths: Iterable[Path], events: Sequence[NPTEvent]) -> IntegrityReport:
    """Compare the events against the reports they claim to come from.

    `paths` must be the documents the events were drawn from. A document with no event is still
    checked, because a block that should have produced one and did not is the defect this pass
    mark exists to catch, and it is invisible if the document is skipped for being empty.
    """
    by_document: dict[str, list[NPTEvent]] = {}
    for event in events:
        by_document.setdefault(event.source_document, []).append(event)

    findings: list[IntegrityFinding] = []
    qualifying = 0
    checked = 0
    durations = 0
    documents = 0

    duplicate_ids = [i for i, n in Counter(e.event_id for e in events).items() if n > 1]
    for event_id in sorted(duplicate_ids):
        findings.append(
            IntegrityFinding(
                kind="duplicate_event_id",
                source_document=next(e.source_document for e in events if e.event_id == event_id),
                detail=f"{event_id} appears on more than one event",
            )
        )

    for path in sorted(set(paths)):
        documents += 1
        root = parse_xml_file(path)
        found = by_document.get(path.name, [])

        # Pair by the one thing both sides derive independently from the source: the block's
        # start time and its activity code. Pairing by event id would use the extractor's own
        # id scheme to check the extractor.
        remaining = {(e.start_time, e.activity_code): e for e in found}
        if len(remaining) != len(found):
            findings.append(
                IntegrityFinding(
                    kind="unexpected_event",
                    source_document=path.name,
                    detail=(
                        f"{len(found)} events collapse to {len(remaining)} distinct "
                        "(start time, activity code) pairs, so at least two describe one block"
                    ),
                )
            )

        for report in root.iter(f"{WITSML_NS}drillReport"):
            for activity in report.iter(f"{WITSML_NS}activity"):
                code = _text(activity, "proprietaryCode")
                state = _text(activity, "state")
                start = _timestamp(_text(activity, "dTimStart"))
                end = _timestamp(_text(activity, "dTimEnd"))
                qualifies = is_non_productive(code, state)

                if not qualifies:
                    if start is not None and (start, code) in remaining:
                        findings.append(
                            IntegrityFinding(
                                kind="unexpected_event",
                                source_document=path.name,
                                detail=f"{code!r} at {start.isoformat()} does not meet the "
                                f"section 14.1 rule but produced an event",
                            )
                        )
                    continue

                qualifying += 1
                if start is None or end is None:
                    findings.append(
                        IntegrityFinding(
                            kind="untimed_block",
                            source_document=path.name,
                            detail=f"{code!r} meets the rule but has no usable timestamps",
                        )
                    )
                    continue

                if (start, code) not in remaining:
                    findings.append(
                        IntegrityFinding(
                            kind="missing_event",
                            source_document=path.name,
                            detail=f"{code!r} at {start.isoformat()} meets the section 14.1 "
                            "rule but produced no event",
                        )
                    )
                    continue
                event = remaining.pop((start, code))

                checked += 1
                durations += 1
                expected = (end - start).total_seconds() / 3600.0
                if abs(event.duration_hours - expected) > DURATION_TOLERANCE_HOURS:
                    findings.append(
                        IntegrityFinding(
                            kind="duration_mismatch",
                            source_document=path.name,
                            detail=(
                                f"{event.event_id}: stored {event.duration_hours:.4f} h, "
                                f"timestamps give {expected:.4f} h"
                            ),
                        )
                    )

        for (start_time, code), orphan in sorted(remaining.items(), key=lambda kv: kv[0][0]):
            findings.append(
                IntegrityFinding(
                    kind="unexpected_event",
                    source_document=path.name,
                    detail=f"{orphan.event_id} claims {code!r} at {start_time.isoformat()}, "
                    "which is not a qualifying block in this document",
                )
            )

    return IntegrityReport(
        documents=documents,
        qualifying_blocks=qualifying,
        events_checked=checked,
        durations_checked=durations,
        findings=tuple(findings),
    )
