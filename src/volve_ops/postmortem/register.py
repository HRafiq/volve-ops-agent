"""The cross-well lessons register of protocol section 20.4.

A pattern is a distinct `(activity subcategory, detail state)` pair, taken from the source's own
fields. That choice matters more than it looks: grouping by cause label would make the register
inherit section 17's limitation, since the labels are machine-assisted and cover 135 of 3,673
events.
Grouping by what the operator filed carries no such dependency, and the labelled fraction of each
pattern is reported instead as the only honest statement of how well understood it is.

A pattern is **recurring** when it appears on at least three development wells and accounts for at
least twenty-four hours. Both numbers are fixed in section 20.4 and neither moves: three wells
because
two is a coincidence, and a rig-day because below it a lesson is indistinguishable from how a
particular morning happened to be written up.

What the register is not: a claim that a recurring pattern reflects a real operational cause. It
reports what recurs in the record. Section 20.7 defers the question of whether a lesson is a correct
lesson, for the reason sections 17, 18 and 19 each give.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.extraction.npt import NPTEvent

#: Section 20.4's thresholds. Fixed before the register was built, and exempt from the convenience
#: of
#: discovering that a slightly lower bar would have produced a longer list.
MIN_WELLS: Final[int] = 3
MIN_HOURS: Final[float] = 24.0


class Occurrence(BaseModel):
    """One citable event behind a pattern. The register quotes, it does not paraphrase."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    well: str
    source_document: str
    report_date: str
    duration_hours: float
    span: str

    @property
    def locator(self) -> str:
        return f"{self.source_document}#{self.event_id}"


class Pattern(BaseModel):
    """One entry in the register, with everything section 20.4 requires of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subcategory: str
    detail_state: str
    wells: tuple[str, ...]
    events: int
    total_hours: float
    first_seen: str
    last_seen: str
    representative: Occurrence
    labelled_events: int

    @property
    def recurring(self) -> bool:
        return len(self.wells) >= MIN_WELLS and self.total_hours >= MIN_HOURS

    @property
    def labelled_fraction(self) -> float:
        """How much of this pattern a human-readable cause has been assigned to.

        Zero for most patterns, and that is the point of reporting it: a pattern with 40 events and
        two labels is a pattern nobody has characterised, however many hours it accounts for.
        """
        return self.labelled_events / self.events if self.events else 0.0

    @property
    def mean_hours(self) -> float:
        return self.total_hours / self.events if self.events else 0.0


class Register(BaseModel):
    """The recurring patterns, and what the thresholds excluded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    patterns: tuple[Pattern, ...]
    excluded_patterns: int
    excluded_hours: float
    corpus_hours: float
    wells: tuple[str, ...]

    @property
    def recurring_hours(self) -> float:
        return sum(p.total_hours for p in self.patterns)

    @property
    def coverage(self) -> float:
        """The share of non-productive hours the recurring patterns account for.

        Reported, never gated. Section 20.4 says why: how concentrated a corpus happens to be is a
        property of the data, and a bar fixed against it would be a bar on the dataset.
        """
        return self.recurring_hours / self.corpus_hours if self.corpus_hours > 0 else 0.0


def _first_sentence(text: str) -> str:
    """A verbatim span for citation: the comment's first sentence, or the comment.

    Verbatim because the register is quoted back to a reader who may check it, and section 20.6
    gates
    on every quoted span being a substring of the event it cites.
    """
    for piece in text.replace("\n", ". ").split(". "):
        trimmed = piece.strip()
        if len(trimmed) >= 12 and trimmed in text:
            return trimmed
    return text.strip()


def build(
    events: Sequence[NPTEvent],
    *,
    wells: Iterable[str],
    labelled_event_ids: Iterable[str] = (),
) -> Register:
    """Group the events into patterns and keep the ones that recur.

    `wells` is the development-well set. It is required rather than defaulted, because section 20.1
    confines the post-mortem to development wells and a default would make the restriction something
    a
    caller could forget.
    """
    permitted = set(wells)
    labelled = set(labelled_event_ids)
    in_scope = [e for e in events if e.well in permitted]

    grouped: dict[tuple[str, str], list[NPTEvent]] = {}
    for event in in_scope:
        grouped.setdefault((event.subcategory, event.state_detail), []).append(event)

    patterns: list[Pattern] = []
    excluded_count = 0
    excluded_hours = 0.0

    for (subcategory, detail), group in sorted(grouped.items()):
        ordered = sorted(group, key=lambda e: (e.report_date, e.event_id))
        hours = sum(e.duration_hours for e in ordered)
        group_wells = tuple(sorted({e.well for e in ordered}))
        # The longest event, so the quoted span is the one that cost the most time rather than
        # whichever happened to come first.
        longest = max(ordered, key=lambda e: (e.duration_hours, e.event_id))
        pattern = Pattern(
            subcategory=subcategory,
            detail_state=detail,
            wells=group_wells,
            events=len(ordered),
            total_hours=hours,
            first_seen=ordered[0].report_date.isoformat(),
            last_seen=ordered[-1].report_date.isoformat(),
            representative=Occurrence(
                event_id=longest.event_id,
                well=longest.well,
                source_document=longest.source_document,
                report_date=longest.report_date.isoformat(),
                duration_hours=longest.duration_hours,
                span=_first_sentence(longest.comment),
            ),
            labelled_events=sum(1 for e in ordered if e.event_id in labelled),
        )
        if pattern.recurring:
            patterns.append(pattern)
        else:
            excluded_count += 1
            excluded_hours += hours

    # Sorted by hours, then by name, so the order is reproducible: section 20.6 gates on it.
    patterns.sort(key=lambda p: (-round(p.total_hours, 6), p.subcategory, p.detail_state))
    return Register(
        patterns=tuple(patterns),
        excluded_patterns=excluded_count,
        excluded_hours=excluded_hours,
        corpus_hours=sum(e.duration_hours for e in in_scope),
        wells=tuple(sorted(permitted)),
    )


def cost_equivalent(hours: float, day_rate_usd: float | None) -> tuple[float | None, str]:
    """Estimated rig-time cost equivalent, and the assumption it rests on.

    Returns `(None, "")` when no rate is supplied, which is the default everywhere. Section 20.3
    forbids a built-in day rate: a rig rate is a commercial negotiation this project has no access
    to,
    and an illustration that circulates as a finding is the failure mode. The assumption travels
    with
    the number so the two cannot be separated by a copy and paste.
    """
    if day_rate_usd is None:
        return None, ""
    return (
        hours / 24.0 * day_rate_usd,
        f"at a stated assumption of {day_rate_usd:,.0f} USD per rig day, which is an illustration "
        f"and not a market rate",
    )


def days_between(first: str, last: str) -> int:
    """Calendar span of a pattern, for the register's first and last occurrence columns."""
    return (dt.date.fromisoformat(last) - dt.date.fromisoformat(first)).days
