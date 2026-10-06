"""The bounded controller of protocol section 18.

The controller owns the stage sequence and the stop conditions. A model's judgement enters at
exactly two points, declared in `Judgement` below: how to phrase a retrieval query, and whether
another evidence pass is justified. It is never asked what to do next from an open list of tools,
which is the thing section 18.1 forbids and which the recorded stage sequence makes checkable.

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
EVIDENCE_WINDOW_DAYS: Final[int] = 45
OFFSET_FIELD_WIDE_DROP: Final[float] = -0.20


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

    _TERMS: Final[dict[str, str]] = {
        "H-choke": "choke reduced rate production restriction",
        "H-uptime": "shut in downtime production stop",
        "H-water": "water cut injection breakthrough",
        "H-pressure": "pressure drawdown reservoir decline",
        "H-field": "platform shutdown field process trip",
    }

    def retrieval_query(
        self, bundle: DiagnosticBundle, hypotheses: Sequence[Hypothesis], pass_number: int
    ) -> str:
        open_ones = [h for h in hypotheses if h.status is HypothesisStatus.PLAUSIBLE]
        chosen = open_ones[pass_number % len(open_ones)] if open_ones else None
        if chosen is None:
            return "well intervention production"
        return self._TERMS.get(chosen.hypothesis_id, chosen.description)

    def another_pass(self, hypotheses: Sequence[Hypothesis], pass_number: int, found: int) -> bool:
        if found == 0:
            return False
        return any(h.status is HypothesisStatus.PLAUSIBLE for h in hypotheses)


class ReplayJudgement:
    """Replays the judgements a trace recorded, so a finding is recomputed rather than read back.

    This is what makes section 18.7's replay pass mark a determinism test on the controller: if any
    ordering, timestamp or unseeded choice leaks into the finding, replay produces a different one.
    """

    name = "replay"

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
    relative = (
        None if comparison.relative_shift is None else comparison.relative_shift * direction
    )
    return comparison.standardised_shift * direction, relative


def _status(
    signal: float | None, relative: float | None, *, available: bool
) -> HypothesisStatus:
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
            status=_status(
                pressure, pressure_relative, available=avail(Channel.DOWNHOLE_PRESSURE)
            ),
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


def _attach(
    hypotheses: list[Hypothesis],
    hypothesis_id: str,
    refs: Sequence[EvidenceRef],
) -> int:
    """Attach retrieved evidence, raising plausibility but never to supported.

    A lexical match is not evidence of a mechanism, so retrieval under a rule-based judgement can
    make a hypothesis worth keeping open and cannot make it supported. That ceiling is the thing a
    model-backed role would have to beat, and leaving it unstated would make the baseline look
    stronger than it is.
    """
    added = 0
    for index, hypothesis in enumerate(hypotheses):
        if hypothesis.hypothesis_id != hypothesis_id or not refs:
            continue
        status = hypothesis.status
        if status in {HypothesisStatus.UNRESOLVED, HypothesisStatus.WEAK}:
            status = HypothesisStatus.PLAUSIBLE
        hypotheses[index] = hypothesis.model_copy(
            update={
                "supporting": (*hypothesis.supporting, *refs),
                "status": status,
            }
        )
        added = len(refs)
    return added


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

    lines = [f"Well {bundle.well} produced below expectation over the episode window."]
    if supported:
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
    documents: Mapping[str, str],
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
        open_ones = [h for h in hypotheses if h.status is HypothesisStatus.PLAUSIBLE]
        target = open_ones[pass_number % len(open_ones)].hypothesis_id if open_ones else "H-choke"
        # The date range goes to the index rather than filtering its output: asking for three
        # hits on the well and then discarding those outside the window returned nothing at all,
        # because a well's three best lexical matches are usually years from any one episode.
        hits = index.search(
            query,
            limit=5,
            well=episode.well,
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
            and span in documents.get(hit.chunk.chunk_id, "")
        )
        recorder.record(
            Stage.RETRIEVE_EVIDENCE,
            f"pass {pass_number}: query {query!r}, {len(hits)} hits, "
            f"{len(in_window)} inside the window, {len(refs)} citable",
            judgement_key=f"retrieval_query:{pass_number}",
            judgement=query,
        )

        added = _attach(hypotheses, target, refs)
        recorder.record(
            Stage.SEEK_CONTRADICTION,
            f"attached {added} refs to {target}; "
            f"contradicted {_ids(hypotheses, HypothesisStatus.CONTRADICTED)}",
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
        )
        pass_number += 1
        if not keep_going:
            if any(h.status is HypothesisStatus.PLAUSIBLE for h in hypotheses):
                stop = StopReason.EVIDENCE_EXHAUSTED
            else:
                stop = StopReason.EVIDENCE_THRESHOLD_MET
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


def _within(report_date: str, onset: dt.date, offset: dt.date, *, days: int) -> bool:
    """Whether a report falls near the episode. A report just before onset is what explains it."""
    try:
        when = dt.date.fromisoformat(report_date)
    except ValueError:  # pragma: no cover - chunk dates are written by the extractor
        return False
    return (onset - dt.timedelta(days=days)) <= when <= (offset + dt.timedelta(days=days))


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
