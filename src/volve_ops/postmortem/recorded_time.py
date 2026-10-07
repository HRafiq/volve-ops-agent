"""The three recorded-time categories of protocol section 20.2, walked from the source.

ADR 0002 fixed the naming after B1 failed: **non-NPT recorded time**, **NPT**, and **other
unclassified time**. The word "productive" is absent on purpose, because nothing in this source
positively identifies productive work, and calling the remainder productive would be inventing a
classification the data does not carry.

This walks every activity block rather than reading the event store, for two reasons. The store
holds
only non-productive events by design, so the other two categories are not in it. And section 20.8's
gate asks for per-well totals verified by a path independent of the extractor, which this is: it
shares
`is_non_productive` with the extractor, because section 14.1's rule is the specification and a
second
copy would test the copy, and nothing else.

Two things it measures rather than assumes. **Concurrent blocks**: block durations sum to slightly
more
than the wall clock they cover, because a few reports record two things happening at once. **Gaps**:
time inside a report that no block covers, which is the third category and is small here. Neither is
folded into a tolerance. Section 20.2 is explicit that a tolerance wide enough to absorb them would
be
wide enough to hide an arithmetic error.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from pathlib import Path
from xml.etree.ElementTree import Element

from pydantic import BaseModel, ConfigDict

from volve_ops.domain.well_naming import canonical_from_ddr_token, well_of
from volve_ops.extraction.npt import WITSML_NS, is_non_productive, parse_report_filename
from volve_ops.ingest.safe_xml import parse_xml_file


class WellTime(BaseModel):
    """One well's recorded time, in the three categories ADR 0002 fixed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    well: str
    npt_hours: float
    non_npt_recorded_hours: float
    unclassified_gap_hours: float
    concurrent_overlap_hours: float
    blocks: int
    npt_blocks: int
    reports: int

    @property
    def block_duration_hours(self) -> float:
        """What the blocks sum to. The reconciliation target of section 20.2."""
        return self.npt_hours + self.non_npt_recorded_hours

    @property
    def npt_share(self) -> float:
        total = self.block_duration_hours
        return self.npt_hours / total if total > 0 else 0.0


class RecordedTime(BaseModel):
    """The whole walk, per well and in total."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    wells: tuple[WellTime, ...]
    untimed_blocks: int
    reports: int

    @property
    def npt_hours(self) -> float:
        return sum(w.npt_hours for w in self.wells)

    @property
    def non_npt_recorded_hours(self) -> float:
        return sum(w.non_npt_recorded_hours for w in self.wells)

    @property
    def unclassified_gap_hours(self) -> float:
        return sum(w.unclassified_gap_hours for w in self.wells)

    @property
    def concurrent_overlap_hours(self) -> float:
        return sum(w.concurrent_overlap_hours for w in self.wells)

    @property
    def blocks(self) -> int:
        return sum(w.blocks for w in self.wells)

    def for_well(self, well: str) -> WellTime | None:
        return next((w for w in self.wells if w.well == well), None)

    def only(self, wells: Iterable[str]) -> RecordedTime:
        """The same walk restricted to these wells.

        Section 20.1 confines the post-mortem to development wells, and restricting here rather than
        at the walk means the excluded share can be reported: a partial total presented as a total
        is
        the thing that disclosure prevents.
        """
        keep = set(wells)
        return RecordedTime(
            wells=tuple(w for w in self.wells if w.well in keep),
            untimed_blocks=self.untimed_blocks,
            reports=self.reports,
        )


def _text(element: Element, tag: str) -> str:
    found = element.find(f"{WITSML_NS}{tag}")
    return (found.text or "").strip() if found is not None and found.text else ""


def _timestamp(raw: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def _coverage(spans: list[tuple[dt.datetime, dt.datetime]]) -> tuple[float, float]:
    """Wall-clock gaps inside a report, and hours of concurrent activity.

    Merging the spans gives the wall clock actually covered. What the blocks sum to, minus that, is
    time counted twice because two things happened at once. What falls between merged spans is time
    no block covers, which is the third category.
    """
    if not spans:
        return 0.0, 0.0
    ordered = sorted(spans)
    merged: list[list[dt.datetime]] = [list(ordered[0])]
    gaps = 0.0
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
            continue
        gaps += (start - merged[-1][1]).total_seconds() / 3600.0
        merged.append([start, end])
    covered = sum((e - s).total_seconds() / 3600.0 for s, e in merged)
    summed = sum((e - s).total_seconds() / 3600.0 for s, e in ordered)
    return gaps, max(0.0, summed - covered)


def walk(report_dir: Path) -> RecordedTime:
    """Total every activity block in the corpus, per well and per category."""
    npt: dict[str, float] = {}
    other: dict[str, float] = {}
    gaps: dict[str, float] = {}
    overlap: dict[str, float] = {}
    blocks: dict[str, int] = {}
    npt_blocks: dict[str, int] = {}
    reports: dict[str, int] = {}
    untimed = 0
    total_reports = 0

    for path in sorted(report_dir.glob("*.xml")):
        token, _ = parse_report_filename(path)
        well = well_of(canonical_from_ddr_token(token))
        total_reports += 1
        reports[well] = reports.get(well, 0) + 1
        spans: list[tuple[dt.datetime, dt.datetime]] = []
        root = parse_xml_file(path)

        for report in root.iter(f"{WITSML_NS}drillReport"):
            for activity in report.iter(f"{WITSML_NS}activity"):
                code = _text(activity, "proprietaryCode")
                state = _text(activity, "state")
                start = _timestamp(_text(activity, "dTimStart"))
                end = _timestamp(_text(activity, "dTimEnd"))
                blocks[well] = blocks.get(well, 0) + 1
                if start is None or end is None:
                    untimed += 1
                    continue
                spans.append((start, end))
                hours = (end - start).total_seconds() / 3600.0
                if is_non_productive(code, state):
                    npt[well] = npt.get(well, 0.0) + hours
                    npt_blocks[well] = npt_blocks.get(well, 0) + 1
                else:
                    other[well] = other.get(well, 0.0) + hours

        gap, concurrent = _coverage(spans)
        gaps[well] = gaps.get(well, 0.0) + gap
        overlap[well] = overlap.get(well, 0.0) + concurrent

    return RecordedTime(
        wells=tuple(
            WellTime(
                well=well,
                npt_hours=npt.get(well, 0.0),
                non_npt_recorded_hours=other.get(well, 0.0),
                unclassified_gap_hours=gaps.get(well, 0.0),
                concurrent_overlap_hours=overlap.get(well, 0.0),
                blocks=blocks.get(well, 0),
                npt_blocks=npt_blocks.get(well, 0),
                reports=reports.get(well, 0),
            )
            for well in sorted(blocks)
        ),
        untimed_blocks=untimed,
        reports=total_reports,
    )
