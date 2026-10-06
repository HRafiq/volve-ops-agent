"""The bounded controller of protocol section 18.

The controller owns the stage sequence and the stop conditions. A model's judgement enters at
exactly two points, declared in `Judgement` below: how to phrase a retrieval query, and whether
another evidence pass is justified. It is never asked what to do next from an open list of tools,
which is the thing section 18.1 forbids.

Section 18.1 as first written named four judgement points rather than two, and amendment 4 records
the difference: which hypothesis to query next is taken here, in a fixed order, and "which report
section to read" has no meaning when the retrieval unit is a single activity comment.

`check_stage_order` refuses a stage sequence this controller could not have produced, and that is a
guard against this code changing rather than a proof that it is bounded today. The stage labels are
assigned here, and a step records no tool identity, so a controller that did something else and
labelled it correctly would pass. Protocol section 18.1 now says so.

Hypothesis formation is deliberately deterministic, from templates driven by the diagnostic bundle.
Section 18.1 gives the model judgement over which hypothesis needs more evidence, not over what the
hypothesis space is. A model inventing its own candidates would make the space unbounded and the
abstention rate uninterpretable, because a system that never considers a hypothesis cannot be scored
on failing to support it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Final, Protocol

from pydantic import BaseModel, ConfigDict

from volve_ops.domain.episodes import Episode
from volve_ops.domain.sensors import Channel
from volve_ops.domain.well_naming import well_of
from volve_ops.investigation import INVESTIGATOR_VERSION
from volve_ops.investigation.diagnostics import DiagnosticBundle
from volve_ops.investigation.schemas import (
    CURTAILED,
    CausalLevel,
    ChannelAvailability,
    EvidenceKind,
    EvidenceRef,
    Finding,
    Hypothesis,
    HypothesisStatus,
    StopReason,
    verdict_for,
)
from volve_ops.investigation.trace import Stage, Trace, TraceRecorder
from volve_ops.investigation.validator import CitableDocument
from volve_ops.provenance.facts import FactLedger
from volve_ops.retrieval.index import BM25Index

#: Thresholds for reading the bundle into hypothesis status. Part of the controller's definition
#: rather than tunable per run: a threshold chosen per episode is a conclusion chosen per episode.
STRONG_SHIFT: Final[float] = 1.0
WEAK_SHIFT: Final[float] = 0.5

#: A movement must also be large in its own units before it can support a hypothesis. Found while
#: testing: a well whose choke sat at 50, 51, 52 for two months has a baseline spread near 0.8, so a
#: drop to 50 is a 1.2-sigma shift and a 2 percent change. Standardising alone would call that a
#: supported explanation for a lost third of the rate, which it plainly is not. Requiring both keeps
#: statistical significance from standing in for physical significance.
MIN_RELATIVE_SHIFT: Final[float] = 0.10
WATER_CUT_RISE: Final[float] = 0.05

#: How far either side of an episode a drilling report may sit and still bear on it. A report just
#: before onset is often what explains the episode, so the window is not the episode alone.
#: Recorded as protocol amendment 4: chosen after the tag, and it changes which documents an
#: investigation can see, so it is a post-inspection parameter and is labelled as one.
EVIDENCE_WINDOW_DAYS: Final[int] = 45

#: Phrases that mark a document stating *why* something was done rather than only what. Reaching
#: `documented_root_cause` needs a cited span containing one of these alongside a hypothesis the
#: structured data already supports: the data establishes what changed, the document why.
#:
#: This is a lexical proxy for a judgement and is weaker than a model would be. It is here because
#: the first version of this controller could not emit the top causal level by any path, which made
#: project's published claim that the level was unreached "for want of documents" untestable.
INTENT_MARKERS: Final[tuple[str, ...]] = (
    "to prepare",
    "in preparation",
    "in order to",
    "due to",
    "because of",
    "for the purpose",
    "as per",
    "according to programme",
    "planned",
    "requested by",
)


class Budget(BaseModel):
    """Step and cost caps. A breach is a reported stop condition, never a silent truncation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_steps: int = 24
    max_cost_usd: float = 0.25
    max_evidence_passes: int = 3


class Judgement(Protocol):
    """The two points at which a model's judgement enters a bounded investigation.

    Keeping the surface this small is the design. A wider interface would let the model reshape the
    investigation, and then the trace would record a different workflow on every run.
    """

    name: str
    cost_per_call_usd: float
    """What one judgement call costs. Zero for a deterministic role.

    It exists so that `cost_budget_reached` is reachable at all. Review found the condition listed
    in the protocol, in `CURTAILED` and in the pass-mark checks, while nothing in the codebase could
    ever set a cost. That made it decoration.
    """

    def retrieval_query(
        self, bundle: DiagnosticBundle, hypotheses: Sequence[Hypothesis], pass_number: int
    ) -> str:
        """How to phrase this pass's search of the drilling narrative."""
        ...

    def another_pass(self, hypotheses: Sequence[Hypothesis], pass_number: int, found: int) -> bool:
        """Whether another evidence pass is justified."""
        ...


class RuleBasedJudgement:
    """The deterministic judgement, and the floor any model-backed role has to beat.

    No API key is required to run an investigation with this, which matters for two reasons beyond
    convenience. A controller whose correctness depends on a model is a controller nobody can test.
    And section 18.6 needs an opponent that was fixed before any model ran: this one phrases queries
    from the hypotheses the bundle produced and stops when a pass adds nothing.
    """

    name = "rule-based"
    cost_per_call_usd = 0.0

    _TERMS: Final[dict[str, str]] = {
        "H-choke": "choke reduced closed in well restriction handover",
        "H-uptime": "shut in downtime production stop closed",
        "H-water": "water cut injection breakthrough",
        "H-pressure": "pressure drawdown reservoir decline",
        "H-field": "platform shutdown field process trip",
    }

    def retrieval_query(
        self, bundle: DiagnosticBundle, hypotheses: Sequence[Hypothesis], pass_number: int
    ) -> str:
        """Query the next hypothesis worth testing, supported ones included.

        The first version drew only from `plausible`, so the hypothesis a finding rested on was
        never put to the documents. Review found a report dated one day before an episode's onset
        that the controller had been built never to ask about.
        """
        order = testable(hypotheses)
        if not order:
            return "well intervention production"
        return self._TERMS.get(
            order[pass_number % len(order)].hypothesis_id,
            order[pass_number % len(order)].description,
        )

    def another_pass(self, hypotheses: Sequence[Hypothesis], pass_number: int, found: int) -> bool:
        """Continue while a hypothesis worth testing has not been asked about yet.

        Not "while the last pass found something", which was the first version and which made every
        run exactly one pass long and `max_evidence_passes` dead.
        """
        return pass_number + 1 < len(testable(hypotheses))


class ReplayJudgement:
    """Replays the judgements a trace recorded, so a finding is recomputed rather than read back.

    This is what makes section 18.7's replay pass mark a determinism test on the controller: if any
    ordering, timestamp or unseeded choice leaks into the finding, replay produces a different one.
    """

    name = "replay"
    cost_per_call_usd = 0.0

    def __init__(self, trace: Trace) -> None:
        self._judgements = trace.judgements

    def retrieval_query(
        self, bundle: DiagnosticBundle, hypotheses: Sequence[Hypothesis], pass_number: int
    ) -> str:
        key = f"retrieval_query:{pass_number}"
        value = self._judgements.get(key)
        if not isinstance(value, str):
            raise KeyError(f"the trace records no {key}")
        return value

    def another_pass(self, hypotheses: Sequence[Hypothesis], pass_number: int, found: int) -> bool:
        key = f"another_pass:{pass_number}"
        value = self._judgements.get(key)
        if not isinstance(value, bool):
            raise KeyError(f"the trace records no {key}")
        return value


def testable(hypotheses: Sequence[Hypothesis]) -> list[Hypothesis]:
    """The hypotheses a document could still say something about, in a fixed order.

    Supported ones are included: a document explaining *why* a supported change was made is what
    lifts it to `documented_root_cause`, and that is the whole purpose of the retrieval stage.
    Contradicted ones are excluded, and so are unresolved ones, whose channel is missing, because no
    narrative recovers a measurement that was never taken.
    """
    return [
        h
        for h in hypotheses
        if h.status in {HypothesisStatus.SUPPORTED, HypothesisStatus.PLAUSIBLE}
    ]


class InvestigationResult(BaseModel):
    """A finding and the trace that produced it, or the reason there is no finding."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding: Finding | None
    trace: Trace
    baseline_agreement: bool | None = None


def _signed(
    bundle: DiagnosticBundle, channel: Channel, direction: int
) -> tuple[float | None, float | None]:
    """The channel's movement, standardised and relative, both signed so that positive means
    "consistent with losing rate"."""
    comparison = bundle.comparison(channel)
    if comparison is None or comparison.standardised_shift is None:
        return None, None
    relative = None if comparison.relative_shift is None else comparison.relative_shift * direction
    return comparison.standardised_shift * direction, relative


def _status(signal: float | None, relative: float | None, *, available: bool) -> HypothesisStatus:
    """Read one channel's movement into a status.

    Three distinctions the simpler version lost. A channel that is absent is `unresolved`, not
    `weak`: no movement was observed because nothing was measured. A movement that is large in
    sigma but small in its own units is `plausible` rather than `supported`, per
    `MIN_RELATIVE_SHIFT`. And a movement in the direction that would have *raised* rate contradicts
    the hypothesis rather than merely failing to support it.
    """
    if not available or signal is None:
        return HypothesisStatus.UNRESOLVED
    material = relative is None or abs(relative) >= MIN_RELATIVE_SHIFT
    if signal >= STRONG_SHIFT:
        return HypothesisStatus.SUPPORTED if material else HypothesisStatus.PLAUSIBLE
    if signal >= WEAK_SHIFT:
        return HypothesisStatus.PLAUSIBLE
    if signal <= -STRONG_SHIFT:
        return HypothesisStatus.CONTRADICTED
    return HypothesisStatus.WEAK


def form_hypotheses(bundle: DiagnosticBundle) -> list[Hypothesis]:
    """The candidate set, from templates driven by the bundle. Deterministic by design."""
    unavailable = set(bundle.unavailable_mandatory)

    def avail(*channels: Channel) -> bool:
        return not any(c in unavailable for c in channels)

    choke, choke_relative = _signed(bundle, Channel.CHOKE_SIZE, -1)
    uptime, uptime_relative = _signed(bundle, Channel.ON_STREAM_HOURS, -1)
    pressure, pressure_relative = _signed(bundle, Channel.DOWNHOLE_PRESSURE, -1)

    before = bundle.baseline_rates.median_water_cut
    during = bundle.episode_rates.median_water_cut
    water_rise = None if before is None or during is None else during - before
    water_status = HypothesisStatus.UNRESOLVED
    if water_rise is not None:
        if water_rise >= WATER_CUT_RISE:
            water_status = HypothesisStatus.SUPPORTED
        elif water_rise > 0.0:
            water_status = HypothesisStatus.PLAUSIBLE
        else:
            water_status = HypothesisStatus.CONTRADICTED

    field = bundle.offsets
    field_status = HypothesisStatus.CONTRADICTED
    if not field.wells:
        field_status = HypothesisStatus.UNRESOLVED
    elif field.field_wide:
        field_status = HypothesisStatus.SUPPORTED
    elif field.wells_also_down:
        field_status = HypothesisStatus.PLAUSIBLE

    return [
        Hypothesis(
            hypothesis_id="H-choke",
            description="The choke was reduced, cutting the rate the well could deliver.",
            causal_level=CausalLevel.PROXIMATE_DRIVER,
            status=_status(choke, choke_relative, available=avail(Channel.CHOKE_SIZE)),
            required_channels=(Channel.CHOKE_SIZE,),
            strength_features={"choke_standardised_shift": choke} if choke is not None else {},
        ),
        Hypothesis(
            hypothesis_id="H-uptime",
            description="On-stream time fell, so less of each day was spent producing.",
            causal_level=CausalLevel.PROXIMATE_DRIVER,
            status=_status(uptime, uptime_relative, available=avail(Channel.ON_STREAM_HOURS)),
            required_channels=(Channel.ON_STREAM_HOURS,),
            strength_features={"uptime_standardised_shift": uptime} if uptime is not None else {},
        ),
        Hypothesis(
            hypothesis_id="H-water",
            description="Water cut rose, displacing oil in the produced stream.",
            causal_level=CausalLevel.SUPPORTED_MECHANISM,
            status=water_status,
            required_channels=(),
            strength_features={"water_cut_rise": water_rise} if water_rise is not None else {},
        ),
        Hypothesis(
            hypothesis_id="H-pressure",
            description="Downhole pressure declined, reducing drawdown.",
            causal_level=CausalLevel.SUPPORTED_MECHANISM,
            status=_status(pressure, pressure_relative, available=avail(Channel.DOWNHOLE_PRESSURE)),
            required_channels=(Channel.DOWNHOLE_PRESSURE,),
            missing_evidence=()
            if avail(Channel.DOWNHOLE_PRESSURE)
            else ("no usable downhole pressure for this well over this period",),
            strength_features={"pressure_standardised_shift": pressure}
            if pressure is not None
            else {},
        ),
        Hypothesis(
            hypothesis_id="H-field",
            description="A field-wide constraint reduced output across several wells.",
            causal_level=CausalLevel.PROXIMATE_DRIVER,
            status=field_status,
            required_channels=(),
            strength_features={
                "offset_median_rate_change": field.median_rate_change_fraction,
                "wells_also_down": float(len(field.wells_also_down)),
            }
            if field.median_rate_change_fraction is not None
            else {"wells_also_down": float(len(field.wells_also_down))},
        ),
    ]


def _first_sentence_with(text: str, terms: Sequence[str]) -> str | None:
    """A verbatim substring of the comment that contains a matched term.

    The span has to be literally in the text, because the provenance gate checks exactly that. The
    first sentence carrying a term is enough to let a reviewer see the context without quoting the
    whole comment back.
    """
    lowered = text.lower()
    for raw in text.replace("\n", ". ").split(". "):
        piece = raw.strip()
        if piece and any(t in piece.lower() for t in terms) and piece in text:
            return piece
    return next((text for t in terms if t in lowered), None)


def _states_a_reason(refs: Sequence[EvidenceRef]) -> bool:
    """Whether any cited span says why, rather than only what."""
    return any(
        ref.span is not None and any(m in ref.span.lower() for m in INTENT_MARKERS) for ref in refs
    )


def _attach(
    hypotheses: list[Hypothesis],
    hypothesis_id: str,
    refs: Sequence[EvidenceRef],
) -> tuple[int, bool]:
    """Attach retrieved evidence. Returns how many refs landed, and whether a level was raised.

    Two ceilings, both deliberate. A bare lexical match cannot make a hypothesis supported, because
    matching a term is not evidence of a mechanism: it can only move an unresolved or weak
    hypothesis to plausible. But a span that states a *reason*, landing on a hypothesis the data
    already supports, does lift it to `documented_root_cause`. The data established what changed and
    the document says why, which is what section 18.4 requires of that level.

    The reason test is lexical, so it is weaker than a model's judgement and is documented as such.
    It exists because without it no code path could emit the top level at all, which made this
    project's published claim about why the level was unreached impossible to test.
    """
    added = 0
    raised = False
    for index, hypothesis in enumerate(hypotheses):
        if hypothesis.hypothesis_id != hypothesis_id or not refs:
            continue
        status = hypothesis.status
        level = hypothesis.causal_level
        if status in {HypothesisStatus.UNRESOLVED, HypothesisStatus.WEAK}:
            status = HypothesisStatus.PLAUSIBLE
        if status is HypothesisStatus.SUPPORTED and _states_a_reason(refs):
            level = CausalLevel.DOCUMENTED_ROOT_CAUSE
            raised = True
        hypotheses[index] = hypothesis.model_copy(
            update={
                "supporting": (*hypothesis.supporting, *refs),
                "status": status,
                "causal_level": level,
            }
        )
        added = len(refs)
    return added, raised


def _narrative(
    bundle: DiagnosticBundle,
    hypotheses: Sequence[Hypothesis],
    stop: StopReason,
) -> str:
    """The finding's prose, built so it states no figure the ledger does not carry.

    Section 18.5 rule 3 blocks a narrative holding a number with no fact behind it, and the simplest
    way to satisfy a gate is to make the text that reaches it incapable of breaking the rule. The
    quantities live in the finding's fact ids, which is where a reader can check them.
    """
    supported = [h for h in hypotheses if h.status is HypothesisStatus.SUPPORTED]
    contradicted = [h for h in hypotheses if h.status is HypothesisStatus.CONTRADICTED]
    unresolved = [h for h in hypotheses if h.status is HypothesisStatus.UNRESOLVED]
    documented = [h for h in supported if h.causal_level is CausalLevel.DOCUMENTED_ROOT_CAUSE]

    lines = [f"Well {bundle.well} produced below expectation over the episode window."]
    if documented:
        # Section 18.4's third row is the only wording that may claim a root cause, and a finding
        # that reached the level must say so rather than repeating the disclosure for a lower one.
        # An earlier version always appended "Root cause unresolved", which contradicted the level
        # on the one episode that reached it.
        drivers = "; ".join(h.description for h in documented)
        spans = [
            f"{ref.span!r} in {ref.document}"
            for h in documented
            for ref in h.supporting
            if ref.span is not None
        ]
        lines.append(f"Root cause documented: {drivers}")
        if spans:
            lines.append("Stated in " + "; ".join(spans[:2]) + ".")
    elif supported:
        drivers = "; ".join(h.description for h in supported)
        levels = {h.causal_level for h in supported}
        if levels == {CausalLevel.PROXIMATE_DRIVER}:
            lines.append(f"Proximate driver identified: {drivers}")
            lines.append("Root cause unresolved: the available reports do not explain why.")
        else:
            lines.append(f"Mechanism supported: {drivers}")
            lines.append("Root cause unresolved: no report states the reason for the change.")
    else:
        lines.append("No hypothesis reached support on the evidence available.")

    if contradicted:
        lines.append(
            "Ruled out on the structured data: "
            + "; ".join(h.hypothesis_id for h in contradicted)
            + "."
        )
    if unresolved:
        lines.append(
            "Left unresolved for want of evidence: "
            + "; ".join(h.hypothesis_id for h in unresolved)
            + "."
        )
    if stop in CURTAILED:
        lines.append(f"This investigation was curtailed: {stop.value}.")
    return " ".join(lines)


def investigate(
    episode: Episode,
    bundle: DiagnosticBundle,
    index: BM25Index,
    documents: Mapping[str, CitableDocument],
    ledger: FactLedger,
    *,
    judgement: Judgement | None = None,
    budget: Budget | None = None,
    oil_price_usd_per_sm3: float | None = None,
    correction_store_version: str | None = None,
) -> InvestigationResult:
    """Run one bounded investigation, recording a trace that replays to the same finding."""
    role = judgement or RuleBasedJudgement()
    caps = budget or Budget()
    recorder = TraceRecorder(
        investigator_version=INVESTIGATOR_VERSION,
        well=episode.well,
        episode_onset=episode.onset.isoformat(),
    )

    recorder.record(
        Stage.VALIDATE_REQUEST,
        f"episode {episode.well} {episode.onset}..{episode.offset}, "
        f"{episode.valid_producing_days} valid producing days, "
        f"gaps {episode.gap_fraction:.0%}"
        + (", poorly evidenced" if episode.poorly_evidenced else ""),
    )

    actual = ledger.record(
        "episode_actual_volume",
        episode.deferred_volume_sm3 + episode.cumulative_rate_shortfall_sm3,
        "Sm3",
        source="episode detector",
        locator={"well": episode.well, "onset": episode.onset.isoformat()},
    )
    expected = ledger.record(
        "episode_reference_rate",
        episode.reference_rate_sm3_per_day,
        "Sm3/d",
        source="episode detector",
        locator={"well": episode.well, "onset": episode.onset.isoformat()},
    )
    shortfall = ledger.record(
        "episode_cumulative_rate_shortfall",
        episode.cumulative_rate_shortfall_sm3,
        "Sm3",
        source="episode detector",
        locator={"well": episode.well, "onset": episode.onset.isoformat()},
    )
    value = None
    if oil_price_usd_per_sm3 is not None:
        price = ledger.record(
            "assumed_oil_price",
            oil_price_usd_per_sm3,
            "USD/Sm3",
            source="stated assumption",
            locator={"basis": "documented assumption, not a market quote"},
        )
        value = ledger.derive(
            "estimated_gross_value_shortfall",
            "USD",
            formula="cumulative_rate_shortfall * assumed_oil_price",
            inputs=[shortfall, price],
            compute=lambda a, b: a * b,
            combines_units=True,
        )
    recorder.record(
        Stage.LOAD_EXPECTATION,
        f"recorded {actual.id}, {expected.id}, {shortfall.id}"
        + (f", {value.id}" if value is not None else ", no value without a stated price"),
    )

    recorder.record(
        Stage.DIAGNOSTIC_BUNDLE,
        f"{len(bundle.channels)} mandatory channels; unavailable "
        f"{[c.value for c in bundle.unavailable_mandatory] or 'none'}",
    )

    hypotheses = form_hypotheses(bundle)
    recorder.record(
        Stage.FORM_HYPOTHESES,
        "; ".join(f"{h.hypothesis_id}={h.status.value}" for h in hypotheses),
    )

    stop: StopReason | None = None
    pass_number = 0
    while True:
        if len(recorder.steps) >= caps.max_steps:
            stop = StopReason.STEP_BUDGET_REACHED
            break
        if recorder.cost_usd >= caps.max_cost_usd:
            stop = StopReason.COST_BUDGET_REACHED
            break
        if pass_number >= caps.max_evidence_passes:
            stop = StopReason.EVIDENCE_EXHAUSTED
            break

        query = role.retrieval_query(bundle, hypotheses, pass_number)
        order = testable(hypotheses)
        target = order[pass_number % len(order)].hypothesis_id if order else "H-choke"
        # The date range goes to the index rather than filtering its output: asking for three
        # hits on the well and then discarding those outside the window returned nothing at all,
        # because a well's three best lexical matches are usually years from any one episode.
        # `well_of`, not `episode.well`. An episode names a wellbore, `15/9-F-15 D`, while a chunk
        # names its well, `15/9-F-15`. Filtering on the wellbore silently returned nothing for two
        # of the six development wells, which is exactly how "the documents do not exist" becomes a
        # false conclusion on a different split.
        hits = index.search(
            query,
            limit=5,
            well=well_of(episode.well),
            on_or_after=(episode.onset - dt.timedelta(days=EVIDENCE_WINDOW_DAYS)).isoformat(),
            on_or_before=(episode.offset + dt.timedelta(days=EVIDENCE_WINDOW_DAYS)).isoformat(),
        )
        in_window = list(hits)
        refs = tuple(
            EvidenceRef(
                kind=EvidenceKind.DOCUMENT_SPAN,
                document=hit.chunk.source_document,
                event_id=hit.chunk.chunk_id,
                span=span,
                note=f"matched {list(hit.matched_terms)[:3]}",
            )
            for hit in in_window
            if (span := _first_sentence_with(hit.chunk.text, hit.matched_terms)) is not None
            and hit.chunk.chunk_id in documents
            and span in documents[hit.chunk.chunk_id].text
        )
        recorder.record(
            Stage.RETRIEVE_EVIDENCE,
            f"pass {pass_number}: query {query!r}, {len(hits)} hits, "
            f"{len(in_window)} inside the window, {len(refs)} citable",
            judgement_key=f"retrieval_query:{pass_number}",
            judgement=query,
            cost_usd=role.cost_per_call_usd,
        )

        added, raised = _attach(hypotheses, target, refs)
        recorder.record(
            Stage.SEEK_CONTRADICTION,
            f"attached {added} refs to {target}"
            + ("; raised to documented_root_cause" if raised else "")
            + f"; contradicted {_ids(hypotheses, HypothesisStatus.CONTRADICTED)}",
        )

        if bundle.unavailable_mandatory and any(
            h.status is HypothesisStatus.UNRESOLVED and h.required_channels for h in hypotheses
        ):
            leading = [h for h in hypotheses if h.status is HypothesisStatus.SUPPORTED]
            if not leading:
                stop = StopReason.MANDATORY_EVIDENCE_UNAVAILABLE
                recorder.record(
                    Stage.DECIDE_CONTINUE,
                    "stopping: a channel the open hypotheses need is unavailable",
                    judgement_key=f"another_pass:{pass_number}",
                    judgement=False,
                )
                break

        keep_going = role.another_pass(hypotheses, pass_number, added)
        recorder.record(
            Stage.DECIDE_CONTINUE,
            f"another pass: {keep_going}",
            judgement_key=f"another_pass:{pass_number}",
            judgement=keep_going,
            cost_usd=role.cost_per_call_usd,
        )
        pass_number += 1
        if not keep_going:
            # Amendment 4's wording: "open" means a hypothesis more evidence could still move, which
            # is a plausible one. A weak hypothesis is one whose channel moved slightly, and no
            # amount of narrative turns that into support or a contradiction.
            stop = (
                StopReason.EVIDENCE_EXHAUSTED
                if any(h.status is HypothesisStatus.PLAUSIBLE for h in hypotheses)
                else StopReason.EVIDENCE_THRESHOLD_MET
            )
            break

    assert stop is not None
    verdict = verdict_for(hypotheses)
    narrative = _narrative(bundle, hypotheses, stop)
    availability = tuple(
        ChannelAvailability(
            channel=a.channel, unit=a.unit, days=a.days, usable=a.usable, mandatory=True
        )
        for a in bundle.availability
    )
    finding = Finding(
        finding_id=f"finding_{episode.well.replace('/', '_').replace(' ', '_')}_{episode.onset}",
        well=episode.well,
        episode_onset=episode.onset.isoformat(),
        episode_offset=episode.offset.isoformat(),
        actual_volume_fact_id=actual.id,
        expected_volume_fact_id=expected.id,
        shortfall_fact_id=shortfall.id,
        shortfall_value_fact_id=value.id if value is not None else None,
        oil_price_assumption=(
            None
            if oil_price_usd_per_sm3 is None
            else f"{oil_price_usd_per_sm3} USD/Sm3, a stated assumption and not a market quote"
        ),
        verdict=verdict,
        hypotheses=tuple(hypotheses),
        availability=availability,
        stop_reason=stop,
        curtailed=stop in CURTAILED,
        steps_used=len(recorder.steps) + 2,
        narrative=narrative,
        missing_evidence=tuple(
            sorted({m for h in hypotheses for m in h.missing_evidence}),
        ),
        what_would_change_the_conclusion=_falsifiers(hypotheses, bundle),
        recommended_next_check=_next_check(hypotheses, bundle),
        investigator_version=INVESTIGATOR_VERSION,
        correction_store_version=correction_store_version,
    )
    recorder.record(Stage.COMPOSE_FINDING, f"verdict {verdict.value}, stop {stop.value}")
    recorder.record(Stage.VALIDATE_PROVENANCE, "handed to the section 18.5 gate")
    return InvestigationResult(finding=finding, trace=recorder.finish())


def _ids(hypotheses: Sequence[Hypothesis], status: HypothesisStatus) -> list[str]:
    return [h.hypothesis_id for h in hypotheses if h.status is status]


def _falsifiers(hypotheses: Sequence[Hypothesis], bundle: DiagnosticBundle) -> tuple[str, ...]:
    """What would change the conclusion. Required by section 18.4, and not decoration.

    A conclusion whose falsifier nobody can state is not reviewable, and reviewability is the
    product.
    """
    out: list[str] = []
    for hypothesis in hypotheses:
        if hypothesis.status is HypothesisStatus.SUPPORTED:
            out.append(
                f"{hypothesis.hypothesis_id}: a report showing the change was planned would move "
                "this from a driver to a documented root cause; one showing the channel was "
                "mis-recorded would withdraw it."
            )
        elif hypothesis.status is HypothesisStatus.UNRESOLVED and hypothesis.required_channels:
            channels = ", ".join(c.value for c in hypothesis.required_channels)
            out.append(f"{hypothesis.hypothesis_id}: recovering {channels} would let it be tested.")
    if not out:
        out.append(
            "Any channel recovered for this period, or any report naming an operational change, "
            "would give the first testable hypothesis."
        )
    return tuple(out)


def _next_check(hypotheses: Sequence[Hypothesis], bundle: DiagnosticBundle) -> str:
    """The one thing a person should look at next."""
    if bundle.unavailable_mandatory:
        missing = ", ".join(c.value for c in bundle.unavailable_mandatory)
        return f"Check whether {missing} exists in another source for this period."
    supported = [h for h in hypotheses if h.status is HypothesisStatus.SUPPORTED]
    if supported:
        return (
            f"Read the operations log around {bundle.onset.isoformat()} for a stated reason behind "
            f"{supported[0].hypothesis_id}."
        )
    return f"Review the daily reports for {bundle.well} around {bundle.onset.isoformat()} by hand."
