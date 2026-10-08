"""The cross-well lessons register of protocol section 20.4.

A pattern is a distinct `(activity subcategory, detail state)` pair, taken from the source's own
fields. That choice matters more than it looks: grouping by cause label would make the register
inherit section 17's limitation, since the labels are machine-assisted and cover 135 of the 3,057
development events, 4.4 percent. Grouping by what the operator filed carries no such dependency, and
the labelled fraction of each pattern is reported instead as the only honest statement of how well
understood it is. The denominator is the development events, not the corpus's 3,673: section 16 made
the 616 hold-out events ineligible for labelling, so counting them would measure coverage against a
population no label could have reached.

A pattern is **recurring** when it appears on at least three development wells and accounts for at
least twenty-four hours. Both numbers are fixed in section 20.4 and neither moves: three wells
because two is a coincidence, and a rig-day because below it a lesson is indistinguishable from how
a particular morning happened to be written up.

What the register is not: a claim that a recurring pattern reflects a real operational cause. It
reports what recurs in the record. Section 20.7 defers the question of whether a lesson is a correct
lesson, for the reason sections 17, 18 and 19 each give.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.extraction.npt import NPTEvent

#: Section 20.4's thresholds. Fixed before the register was built, and exempt from the convenience
#: of discovering that a slightly lower bar would have produced a longer list.
MIN_WELLS: Final[int] = 3
MIN_HOURS: Final[float] = 24.0

#: Span limits for a citation. Recorded here and in protocol amendment 7, because section 20
#: promised that every threshold it needs is stated and these two were only in the source.
MIN_SPAN: Final[int] = 12
MAX_SPAN: Final[int] = 160


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
    miscoded_events: int = 0
    """Labelled events whose source coding the labeller flagged as contradicting its own comment.

    Reported per pattern because the grouping key rests on two source fields this project has
    already measured to be unreliable: 21 of 135 labelled events, 15.6 percent, carry a subcategory
    or detail state the comment does not support, and the `echo-statedetail` baseline built from one
    of those fields agrees with the label 48.9 percent of the time. A register that defends its key
    as free of the label dependency, without also saying the key is wrong about one event in six, is
    telling half the story.
    """

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
    def miscoded_fraction(self) -> float:
        """Of the labelled events in this pattern, how many had their source coding flagged.

        Over `labelled_events`, not over `events`: nobody read the unlabelled ones, so a fraction
        over the whole pattern would imply a judgement that was never made.
        """
        return self.miscoded_events / self.labelled_events if self.labelled_events else 0.0


class Register(BaseModel):
    """The recurring patterns, and what the thresholds excluded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    patterns: tuple[Pattern, ...]
    excluded: tuple[Pattern, ...]
    """Patterns the thresholds removed, kept rather than counted.

    Review found the register silently dropping `sidetrack` at 561.5 hours, `lost circulation`,
    `well control` and `casing`: a single well's expensive sequence cannot clear a three-well bar
    however many hours it cost, and those are exactly the shapes an operations reader opens a
    register to find. The bar does not move, and what it excludes is published.
    """
    excluded_hours: float
    corpus_hours: float
    wells: tuple[str, ...]

    @property
    def excluded_patterns(self) -> int:
        return len(self.excluded)

    @property
    def recurring_hours(self) -> float:
        return sum(p.total_hours for p in self.patterns)

    @property
    def labelled_events_in_patterns(self) -> int:
        return sum(p.labelled_events for p in self.patterns)

    @property
    def events_in_patterns(self) -> int:
        return sum(p.events for p in self.patterns)

    @property
    def labelled_fraction_of_patterns(self) -> float:
        """The headline figure: how much of what recurs has a cause label at all.

        A property rather than a number computed in a document. Review found it quoted in bold in
        the results and the README while being computable from neither the manifest nor the harness
        output.
        """
        return (
            self.labelled_events_in_patterns / self.events_in_patterns
            if self.events_in_patterns
            else 0.0
        )

    @property
    def coverage(self) -> float:
        """The share of non-productive hours the recurring patterns account for.

        Reported, never gated. Section 20.4 says why: how concentrated a corpus happens to be is a
        property of the data, and a bar fixed against it would be a bar on the dataset.
        """
        return self.recurring_hours / self.corpus_hours if self.corpus_hours > 0 else 0.0


def _first_sentence(text: str) -> str:
    """A verbatim span for citation: the comment's opening, trimmed at a sentence end.

    Anchored at the start of the comment, which the first version was not. It split on newlines as
    though they ended sentences and then skipped any opening clause under twelve characters, so a
    comment reading `WOC\nMeanwhile: Maintenance...` was cited as "Meanwhile: Maintenance", which
    drops the waiting-on-cement that is the non-productive reason and quotes the concurrent work
    instead. Review found 85 of 3,057 development events would be quoted mid-comment that way.

    So: take the opening, cut at the first sentence terminator if there is one within the limit, and
    otherwise take the first `MAX_SPAN` characters. Verbatim either way, which section 20.6 gates
    on.
    """
    opening = text.strip()
    if not opening:
        return ""
    window = opening[:MAX_SPAN]
    for terminator in (". ", ".\n", "; "):
        cut = window.find(terminator)
        if cut > MIN_SPAN:
            candidate = opening[: cut + 1]
            if candidate in text:
                return candidate
    if window.endswith(".") and window in text:
        return window
    trimmed = window.rstrip()
    return trimmed if trimmed in text else opening[:MAX_SPAN]


def build(
    events: Sequence[NPTEvent],
    *,
    wells: Iterable[str],
    labelled_event_ids: Iterable[str] = (),
    miscoded_event_ids: Iterable[str] = (),
) -> Register:
    """Group the events into patterns and keep the ones that recur.

    `wells` is the development-well set. It is required rather than defaulted, because section 20.1
    confines the post-mortem to development wells and a default would make the restriction something
    a caller could forget.
    """
    permitted = set(wells)
    labelled = set(labelled_event_ids)
    miscoded = set(miscoded_event_ids)
    in_scope = [e for e in events if e.well in permitted]

    grouped: dict[tuple[str, str], list[NPTEvent]] = {}
    for event in in_scope:
        grouped.setdefault((event.subcategory, event.state_detail), []).append(event)

    patterns: list[Pattern] = []
    excluded: list[Pattern] = []
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
            miscoded_events=sum(1 for e in ordered if e.event_id in miscoded),
        )
        if pattern.recurring:
            patterns.append(pattern)
        else:
            excluded.append(pattern)
            excluded_hours += hours

    # Sorted by hours, then by name, so the order is reproducible: section 20.6 gates on it.
    patterns.sort(key=lambda p: (-round(p.total_hours, 6), p.subcategory, p.detail_state))
    excluded.sort(key=lambda p: (-round(p.total_hours, 6), p.subcategory, p.detail_state))
    return Register(
        patterns=tuple(patterns),
        excluded=tuple(excluded),
        excluded_hours=excluded_hours,
        corpus_hours=sum(e.duration_hours for e in in_scope),
        wells=tuple(sorted(permitted)),
    )


def cost_equivalent(hours: float, day_rate_usd: float | None) -> tuple[float | None, str]:
    """Estimated rig-time cost equivalent, and the assumption it rests on.

    Returns `(None, "")` when no rate is supplied, which is the default everywhere. Section 20.3
    forbids a built-in day rate: a rig rate is a commercial negotiation this project has no access
    to, and an illustration that circulates as a finding is the failure mode. The assumption travels
    with the number so the two cannot be separated by a copy and paste.
    """
    if day_rate_usd is None:
        return None, ""
    return (
        hours / 24.0 * day_rate_usd,
        f"at a stated assumption of {day_rate_usd:,.0f} USD per rig day, which is an illustration "
        f"and not a market rate",
    )
