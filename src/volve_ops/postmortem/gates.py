"""Protocol section 20.6's pass marks, as functions rather than as expressions in a script.

Independent review found three of the five gates unable to fail, and its diagnosis is the reason
this module exists: all three lived in `scripts/run_postmortem.py`, the one file with no test.
Across four phases, every gate that could not fail was written in the same file as the thing it
checked, in the same sitting, with no failing case ever executed.

So each gate here is a pure function with a test that makes it fail, and each reports **what it
examined** alongside its verdict, because a gate that passed over an empty set has demonstrated
nothing. The three specific defects, recorded so they are not reintroduced:

- The reconciliation compared the two categories against a property defined as their sum, which is
  `abs(x - x)`. It now compares them against a block total accumulated separately during the walk.
- The hold-out containment check read the development-well list that had just been passed *in* to
  the register, so it tested the negation of its own filter. It now reads the patterns that came
  *out*.
- The currency gate asked the producer function whether it had produced a string. It now reads the
  artifact that gets published.
"""

from __future__ import annotations

import datetime as dt
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from volve_ops.extraction.npt import NPTEvent
from volve_ops.postmortem import corrections, recorded_time, register

#: Section 20.2's tolerance. Floating point and nothing else: this is arithmetic over one set of
#: blocks, so anything wider would be room for a real error to hide in.
RECONCILE_TOLERANCE_HOURS = 0.01

#: A synthetic hold-out well used to probe the correction store's refusal. Synthetic on purpose: the
#: first version probed with a real hold-out event, so the gate failed on a store that correctly
#: held the hold-out back, which is the opposite of what it should reward.
PROBE_WELL = "15/9-F-4"

#: The development well the probes use for the direction that must be accepted, and as the forged
#: well in the probe that must not be. Named here so the two directions cannot drift apart.
PROBE_DEVELOPMENT_WELL = "15/9-F-12"

#: The seven section 20.6 marks, in the order the harness reports them, as the single place their
#: names are written. The consolidated results table imports this rather than retyping them: the
#: first version retyped them here and in the results table, and the two drifted: the table carried
#: both the current names and a stale set naming marks that no longer existed. Every one of them
#: rendered as "not produced" and the coverage gate certified the table complete anyway.
GATE_NAMES: Final[tuple[str, ...]] = (
    "20.6 the corpus is not empty",
    "20.2 categories reconcile and the store agrees on hours and counts",
    "20.6 every citation resolves",
    "20.6 no hold-out well in the post-mortem, the register or the store",
    "20.3 no currency figure without a sound, disclosed assumption",
    "20.5 a hold-out correction is refused at write time",
    "20.6 the register is reproducible",
)


class GateOutcome(BaseModel):
    """One pass mark: whether it held, what it looked at, and what went wrong."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    passed: bool
    examined: int
    detail: tuple[str, ...] = ()

    @property
    def vacuous(self) -> bool:
        """Passed while looking at nothing, which demonstrates nothing."""
        return self.passed and self.examined == 0


def corpus_is_not_empty(
    walked: recorded_time.RecordedTime,
    events: Sequence[NPTEvent],
    built: register.Register,
) -> GateOutcome:
    """A precondition, because every other gate passes trivially on an empty corpus.

    Review ran the whole harness against an empty directory and it reported all five marks passing
    and exited zero. A harness that certifies nothing as clean is worse than one that errors.
    """
    problems: list[str] = []
    if not walked.wells:
        problems.append("the walk found no wells")
    if not events:
        problems.append("the event store is empty")
    if not built.patterns:
        problems.append("the register found no recurring pattern")
    return GateOutcome(
        name="20.6 the corpus is not empty",
        passed=not problems,
        examined=len(walked.wells) + len(events) + len(built.patterns),
        detail=tuple(problems),
    )


def categories_reconcile(
    walked: recorded_time.RecordedTime,
    store_hours: Mapping[str, float],
    store_counts: Mapping[str, int],
) -> GateOutcome:
    """Section 20.2, and the section 20.8 spot-verification, in one gate.

    Three comparisons, and they are not equally strong. Said plainly, because the first version of
    this docstring called all three "two numbers measured separately" and the first of them is not:

    1. The two categories against the walk's block total. Both sides subtract the same pair of
       timestamps, so this cannot detect a wrong duration. What it detects is a block counted twice
       or not at all, which is to say that the two categories **partition** the timed blocks.
    2. This walk's non-productive hours against the **event store's**. Two code paths over the same
       XML, so a disagreement is a real defect in one of them. A **second** path and not an
       independent one: it shares six functions with the extractor, which `recorded_time` lists, and
       section 20.8 says what that leaves the comparison able to establish.
    3. This walk's non-productive **block count** against the store's event count. Hours alone are
       blind to a compensating swap, where one event is dropped and another of equal duration on the
       same well is duplicated; the count is not.
    """
    problems: list[str] = []
    for well in walked.wells:
        if well.reconciliation_error > RECONCILE_TOLERANCE_HOURS:
            problems.append(
                f"{well.well}: categories sum to {well.category_hours:,.2f} h and the blocks to "
                f"{well.summed_block_hours:,.2f} h"
            )
        hours = store_hours.get(well.well, 0.0)
        if abs(well.npt_hours - hours) > RECONCILE_TOLERANCE_HOURS:
            problems.append(
                f"{well.well}: this walk says {well.npt_hours:,.2f} NPT hours, the store says "
                f"{hours:,.2f}"
            )
        count = store_counts.get(well.well, 0)
        if well.npt_blocks != count:
            problems.append(
                f"{well.well}: this walk found {well.npt_blocks} non-productive blocks, the store "
                f"holds {count} events"
            )
    return GateOutcome(
        name="20.2 categories reconcile and the store agrees on hours and counts",
        passed=not problems,
        examined=len(walked.wells),
        detail=tuple(problems),
    )


def citations_resolve(built: register.Register, events: Sequence[NPTEvent]) -> GateOutcome:
    """Every published citation resolves to a real event, document and verbatim span.

    Over the excluded patterns as well as the recurring ones. The first version read
    `built.patterns` alone, while the harness publishes all 38 excluded patterns with their own
    event id, source document and quoted span: a gate covering part of what is published is the
    same mistake as a gate reading its own input.

    An empty span is refused rather than accepted. `"" in comment` is true for every comment, so a
    citation that quoted nothing would have satisfied the verbatim test trivially, which is the
    `abs(x - x)` of substring checks.
    """
    by_id = {e.event_id: e for e in events}
    problems: list[str] = []
    examined = 0
    for label, patterns in (("recurring", built.patterns), ("excluded", built.excluded)):
        for pattern in patterns:
            examined += 1
            ref = pattern.representative
            cited = by_id.get(ref.event_id)
            if cited is None:
                problems.append(f"{label} {ref.event_id} is not in the event store")
                continue
            if not ref.span.strip():
                problems.append(
                    f"{label} {ref.event_id}: the cited span is empty, and an empty span is a "
                    "substring of every comment"
                )
            elif ref.span not in cited.comment:
                problems.append(
                    f"{label} {ref.event_id}: the span is not verbatim in the comment it cites"
                )
            if cited.source_document != ref.source_document:
                problems.append(
                    f"{label} {ref.event_id}: cites {ref.source_document!r}, the event came from "
                    f"{cited.source_document!r}"
                )
            if cited.well != ref.well or ref.well not in pattern.wells:
                problems.append(
                    f"{label} {ref.event_id}: cited well {ref.well!r} is not among the pattern's "
                    "wells"
                )
    return GateOutcome(
        name="20.6 every citation resolves",
        passed=not problems,
        examined=examined,
        detail=tuple(problems[:6]),
    )


def hold_out_is_contained(
    built: register.Register,
    scope: recorded_time.RecordedTime,
    stored_corrections: Sequence[corrections.Correction],
) -> GateOutcome:
    """No hold-out well in anything this phase publishes.

    Reads the register's **output**: the wells each pattern names and the well each citation comes
    from. The first version read the development-well list that had just been passed into
    `register.build`, so it tested the negation of its own filter. Review removed the filter and all
    four hold-out wells appeared in the published patterns while the gate still reported a pass.
    """
    offending: set[str] = set()
    examined = 0
    # Both lists, because both are published. Review removed the register's filter and found one
    # excluded pattern naming only a hold-out well, with its hold-out representative and quoted
    # span, passing a gate that read `built.patterns` alone. Section 20.1 says "not its patterns"
    # and section 20.6 item 3 says "anything published": the excluded table is both.
    for pattern in (*built.patterns, *built.excluded):
        for well in pattern.wells:
            examined += 1
            if corrections.is_hold_out(well):
                offending.add(well)
        examined += 1
        if corrections.is_hold_out(pattern.representative.well):
            offending.add(pattern.representative.well)
    for reported in scope.wells:
        examined += 1
        if corrections.is_hold_out(reported.well):
            offending.add(reported.well)
    for correction in stored_corrections:
        examined += 1
        if corrections.is_hold_out(correction.well):
            offending.add(correction.well)
    return GateOutcome(
        name="20.6 no hold-out well in the post-mortem, the register or the store",
        passed=not offending,
        examined=examined,
        detail=tuple(f"{w} is held out under section 16" for w in sorted(offending)),
    )


def currency_is_disclosed(payload: Mapping[str, Any]) -> GateOutcome:
    """Section 20.3, read off the artifact rather than asked of the producer.

    The first version evaluated `amount is None or bool(assumption)` against the return of
    `cost_equivalent`, whose two branches both satisfy it. Review passed it `nan`, zero and a
    negative rate and it approved all three.
    """
    amount = payload.get("cost_equivalent_usd")
    assumption = payload.get("cost_assumption")
    rate = payload.get("day_rate_usd")
    problems: list[str] = []
    if (amount is None) != (assumption is None):
        problems.append("a currency figure and its assumption must appear or be absent together")
    if amount is not None:
        if (
            not isinstance(amount, int | float)
            or amount != amount
            or amount
            in (
                float("inf"),
                float("-inf"),
            )
        ):
            problems.append(f"the currency figure is not a finite number: {amount!r}")
        if not isinstance(rate, int | float) or not rate or rate <= 0:
            problems.append(f"the day rate is not a positive number: {rate!r}")
        if not isinstance(assumption, str) or "stated assumption" not in assumption:
            problems.append("the assumption does not name itself as a stated assumption")
    return GateOutcome(
        name="20.3 no currency figure without a sound, disclosed assumption",
        passed=not problems,
        examined=1 if amount is not None else 0,
        detail=tuple(problems),
    )


def refusal_is_demonstrated(store: corrections.CorrectionStore) -> GateOutcome:
    """Section 20.5 rule 1, probed in four directions with synthetic corrections.

    Synthetic because the first version probed with a real hold-out event from the store, so the
    gate failed whenever the store correctly contained no hold-out event. A gate that requires
    hold-out data to be present in order to pass is rewarding the wrong thing.

    Four probes, because review got past the first one three times and the gate exercised only the
    weakest path. Each must be refused, and each is a different way a hold-out report reaches the
    store:

    1. A correction on a hold-out well.
    2. A **forged** one: a hold-out event id, a development well, and the hold-out event's comment
       as the old value. This is the one that used to write cleanly, and the one the gate never
       tried.
    3. An event the store cannot place at all, which is what a forged event id looks like.
    4. A development correction whose quoted text carries a hold-out well.

    And one probe that must be accepted, because a store that refuses everything also passes a gate
    that only counts refusals.
    """
    problems: list[str] = []

    def synthetic(event_id: str, well: str, equipment: str) -> NPTEvent:
        """A synthetic event for the probes to correct. Never written anywhere."""
        moment = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
        return NPTEvent(
            event_id=event_id,
            well=well,
            wellbore=well,
            source_document="probe.xml",
            report_date=moment.date(),
            start_time=moment,
            end_time=moment + dt.timedelta(hours=1),
            duration_hours=1.0,
            activity_code="interruption -- wait",
            category="interruption",
            subcategory="wait",
            state="success",
            state_detail="success",
            comment="section 20.6 probe",
            equipment=equipment,
        )

    def probe(**over: Any) -> corrections.Correction:
        fields: dict[str, Any] = {
            "event_id": "probe_hold_out",
            "well": PROBE_WELL,
            "field": corrections.CorrectionField.EQUIPMENT,
            "old_value": "probe pump",
            "new_value": "probe",
            "corrected_by": "gate probe",
            "corrected_at": "1970-01-01T00:00:00+00:00",
            "extractor_version": "extractor-v0",
            "note": "section 20.6 probe, never written",
        }
        fields.update(over)
        return corrections.Correction(**fields)

    held = synthetic("probe_hold_out", PROBE_WELL, "probe pump")
    forged = synthetic("probe_forged", PROBE_WELL, "probe pump")
    development = synthetic("probe_development", PROBE_DEVELOPMENT_WELL, "probe pump")
    quoting = synthetic("probe_quoted", PROBE_DEVELOPMENT_WELL, "probe pump")
    lifted = synthetic("probe_lifted", PROBE_DEVELOPMENT_WELL, "probe pump")

    refusals: tuple[tuple[str, corrections.Correction, Mapping[str, NPTEvent]], ...] = (
        (
            f"a correction naming {PROBE_WELL}",
            probe(),
            {held.event_id: held},
        ),
        (
            "a forged correction carrying a hold-out event under a development well",
            probe(event_id="probe_forged", well=PROBE_DEVELOPMENT_WELL),
            {forged.event_id: forged},
        ),
        (
            "a correction whose event the store cannot place",
            probe(event_id="probe_unplaceable", well=PROBE_DEVELOPMENT_WELL),
            {},
        ),
        (
            "a development correction quoting a hold-out well in its text",
            probe(
                event_id="probe_quoted",
                well=PROBE_DEVELOPMENT_WELL,
                note=f"copied from {PROBE_WELL} report 15_9_F_4_2008_01_01.xml",
            ),
            {quoting.event_id: quoting},
        ),
        # The attack a fourth review measured the text scan cannot see: a hold-out report's
        # verbatim text under an honest development event id and well. Nothing in the metadata is
        # wrong, and the scan catches the well name in only 2.9 percent of this corpus's hold-out
        # comments. What refuses it is that the old value is not what the record says here.
        (
            "a correction whose old value belongs to a different event",
            probe(
                event_id="probe_lifted",
                well=PROBE_DEVELOPMENT_WELL,
                old_value="a value lifted from somewhere else",
            ),
            {lifted.event_id: lifted},
        ),
    )
    with tempfile.TemporaryDirectory() as scratch:
        # Every probe writes to a throwaway directory, the refusing ones included. A refusing probe
        # that reaches the real store leaves a version behind on any store that accepts it, and the
        # store is append-only so nothing could remove it. The first version sandboxed only the
        # accepting probe, which was the one whose reasoning had been written down.
        #
        # `type(store)` so a subclass is probed as itself. A gate that constructed a bare
        # `CorrectionStore` here would test the base class and ignore the store it was handed.
        root = Path(scratch) / "probe-store"
        for index, (description, correction, known) in enumerate(refusals):
            try:
                type(store)(root / f"refuse-{index}").write("probe", [correction], known)
                problems.append(f"{description} was accepted")
            except corrections.HoldOutCorrectionRefused:
                pass

        # The other direction, and it has to be a **write**. The first version built this
        # correction and then only asked `is_hold_out` about its well, which never touches the
        # store, so a store whose `write` raised unconditionally passed with every probe above
        # "refused". Review built exactly that store and the gate approved it.
        allowed = probe(event_id="probe_development", well=PROBE_DEVELOPMENT_WELL)
        if corrections.is_hold_out(allowed.well):
            problems.append(f"{PROBE_DEVELOPMENT_WELL} is being treated as held out")
        try:
            type(store)(root / "accept").write(
                "probe-accepted", [allowed], {development.event_id: development}
            )
        except corrections.HoldOutCorrectionRefused as refused:
            problems.append(
                f"a development correction on {PROBE_DEVELOPMENT_WELL} was refused ({refused}); a "
                "store that refuses everything satisfies every other probe here"
            )
    return GateOutcome(
        name="20.5 a hold-out correction is refused at write time",
        passed=not problems,
        examined=len(refusals) + 2,
        detail=tuple(problems),
    )


def register_is_reproducible(
    built: register.Register,
    events: Sequence[NPTEvent],
    *,
    wells: Sequence[str],
    labelled_event_ids: Sequence[str] = (),
    miscoded_event_ids: Sequence[str] = (),
) -> GateOutcome:
    """Section 20.6 item 5, which was pre-registered, then not implemented, then not falsifiable.

    The protocol listed six pass marks, the script carried five, and the documents were written
    saying five. Review called that the one thing pre-registration exists to prevent, and it was
    right: a gate was dropped and the count rewritten around the drop with no amendment recorded.

    The first implementation then rebuilt the register over reversed input and compared four fields
    of each pattern. A second review showed why that could not fail. `register.build` sorts its
    groups, orders each group by `(report_date, event_id)`, picks the representative by
    `(duration_hours, event_id)` and sorts the patterns by `(-hours, subcategory, detail_state)`;
    every tie is broken by a unique id, so no permutation of the input can change the output. It ran
    4,000 adversarial inputs, duplicate ids and tied durations included, and found no failing case.

    What it checks now is two things that can each fail:

    1. A rebuild over reversed input reproduces **every field of every citation**, not four of
       them, and the excluded patterns as well as the recurring ones. The order-independence this
       asserts is still cheap to satisfy, but the field coverage is what section 20.6 item 5
       actually promised, and the previous key compared neither the quoted span nor the source
       document nor the well list.
    2. The rebuild is compared against **the register the caller is publishing**, not against a
       second register built from different arguments. The first implementation was handed neither
       the labelled ids nor the miscoded ids the published register was built with, so it certified
       the reproducibility of an artifact nobody was publishing. That is the same defect as asking a
       producer function whether it had produced a string, and it is why this gate now takes the
       built register as its first argument.
    """

    def citation(pattern: register.Pattern) -> tuple[Any, ...]:
        """Every field a reader could cite, so a difference in any of them is a difference."""
        return (
            pattern.subcategory,
            pattern.detail_state,
            pattern.wells,
            pattern.events,
            round(pattern.total_hours, 6),
            pattern.first_seen,
            pattern.last_seen,
            pattern.labelled_events,
            pattern.miscoded_events,
            pattern.representative.event_id,
            pattern.representative.well,
            pattern.representative.source_document,
            pattern.representative.report_date,
            round(pattern.representative.duration_hours, 6),
            pattern.representative.span,
        )

    rebuilt = register.build(
        list(reversed(list(events))),
        wells=wells,
        labelled_event_ids=labelled_event_ids,
        miscoded_event_ids=miscoded_event_ids,
    )
    problems: list[str] = []
    examined = 0
    for label, published, second in (
        ("recurring", built.patterns, rebuilt.patterns),
        ("excluded", built.excluded, rebuilt.excluded),
    ):
        if len(published) != len(second):
            problems.append(
                f"{label}: {len(published)} patterns against {len(second)} on a reversed input"
            )
            continue
        for left, right in zip(published, second, strict=True):
            first_citation, other = citation(left), citation(right)
            examined += len(first_citation)
            if first_citation != other:
                differing = [
                    f"field {index}: {a!r} against {b!r}"
                    for index, (a, b) in enumerate(zip(first_citation, other, strict=True))
                    if a != b
                ]
                problems.append(
                    f"{label} {left.subcategory}/{left.detail_state}: " + "; ".join(differing[:3])
                )
    return GateOutcome(
        name="20.6 the register is reproducible",
        passed=not problems,
        examined=examined,
        detail=tuple(problems[:4]),
    )
