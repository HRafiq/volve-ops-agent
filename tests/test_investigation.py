"""The investigation layer: protocol section 18's gates, and the controller's bounds.

Most of these tests exist to make a specific overclaim impossible rather than to exercise a path.
The provenance gate's four rules, the forbidden root-cause wording, the refusal to support a
hypothesis whose channel is missing, and the exactness of trace replay are each a way a finding
could look sound and be unfounded.
"""

from __future__ import annotations

import datetime as dt

import pytest

from volve_ops.domain.day_class import ClassifiedDay, DayClass
from volve_ops.domain.episodes import Episode
from volve_ops.domain.sensors import Channel
from volve_ops.ingest.production import ProductionDay, WellStatus
from volve_ops.investigation import baseline
from volve_ops.investigation.controller import (
    Budget,
    ReplayJudgement,
    RuleBasedJudgement,
    form_hypotheses,
    investigate,
)
from volve_ops.investigation.diagnostics import DiagnosticBundle, build_bundle
from volve_ops.investigation.schemas import (
    CausalLevel,
    ChannelAvailability,
    EvidenceKind,
    EvidenceRef,
    Finding,
    Hypothesis,
    HypothesisStatus,
    StopReason,
    Verdict,
    forbidden_root_cause_wording,
    verdict_for,
)
from volve_ops.investigation.trace import Stage, Trace, TraceError, check_stage_order
from volve_ops.investigation.validator import check
from volve_ops.provenance.facts import FactLedger
from volve_ops.retrieval.index import BM25Index, Chunk

WELL = "15/9-F-12"


def classified(
    when: dt.date,
    *,
    oil: float = 900.0,
    hours: float = 24.0,
    choke: float | None = 50.0,
    pressure: float | None = 230.0,
    whp: float | None = 38.0,
    dp: float | None = 2.4,
    water: float = 10.0,
    day_class: DayClass = DayClass.VALID_PRODUCING,
    well: str = WELL,
) -> ClassifiedDay:
    return ClassifiedDay(
        day=ProductionDay(
            well=well,
            production_date=when,
            on_stream_hours=hours,
            oil_volume_sm3=oil,
            gas_volume_sm3=1000.0,
            water_volume_sm3=water,
            well_status=WellStatus.PRODUCING,
            choke_size=choke,
            downhole_pressure_bar=pressure,
            wellhead_pressure_bar=whp,
            choke_dp_bar=dp,
            source="wb.xlsx",
        ),
        day_class=day_class,
    )


def series(start: dt.date, count: int, **over: object) -> list[ClassifiedDay]:
    return [classified(start + dt.timedelta(days=i), **over) for i in range(count)]  # type: ignore[arg-type]


def episode_of(onset: dt.date, offset: dt.date, well: str = WELL) -> Episode:
    return Episode(
        well=well,
        onset=onset,
        offset=offset,
        valid_producing_days=(offset - onset).days + 1,
        trigger_run_days=7,
        cumulative_rate_shortfall_sm3=5000.0,
        deferred_volume_sm3=1000.0,
        shortfall_threshold_sm3=2000.0,
        reference_rate_sm3_per_day=900.0,
        gap_fraction=0.0,
        open_ended=False,
    )


class TestVerdictIsDerivedNotChosen:
    """A model writing its own verdict is one way a finding overclaims."""

    def hyp(self, status: HypothesisStatus, name: str = "H") -> Hypothesis:
        return Hypothesis(
            hypothesis_id=name,
            description="d",
            causal_level=CausalLevel.PROXIMATE_DRIVER,
            status=status,
        )

    def test_one_supported_is_a_supported_explanation(self) -> None:
        assert verdict_for([self.hyp(HypothesisStatus.SUPPORTED)]) is Verdict.SUPPORTED_EXPLANATION

    def test_two_supported_cannot_be_told_apart(self) -> None:
        pair = [
            self.hyp(HypothesisStatus.SUPPORTED, "A"),
            self.hyp(HypothesisStatus.SUPPORTED, "B"),
        ]
        assert verdict_for(pair) is Verdict.MULTIPLE_PLAUSIBLE_EXPLANATIONS

    def test_a_single_plausible_candidate_is_an_abstention_not_a_result(self) -> None:
        """Calling one weak candidate "multiple plausible explanations" dresses up an abstention."""
        assert verdict_for([self.hyp(HypothesisStatus.PLAUSIBLE)]) is Verdict.INSUFFICIENT_EVIDENCE

    def test_two_plausible_candidates_are_multiple(self) -> None:
        pair = [
            self.hyp(HypothesisStatus.PLAUSIBLE, "A"),
            self.hyp(HypothesisStatus.PLAUSIBLE, "B"),
        ]
        assert verdict_for(pair) is Verdict.MULTIPLE_PLAUSIBLE_EXPLANATIONS

    def test_nothing_standing_is_insufficient_evidence(self) -> None:
        assert (
            verdict_for(
                [
                    self.hyp(HypothesisStatus.CONTRADICTED),
                    self.hyp(HypothesisStatus.UNRESOLVED, "B"),
                ]
            )
            is Verdict.INSUFFICIENT_EVIDENCE
        )


class TestForbiddenWording:
    """Section 18.4: the strongest phrase a reader trusts may not be used below its level."""

    @pytest.mark.parametrize(
        "text",
        [
            "Root cause identified: choke reduction.",
            "The shortfall was caused by a choke change.",
            "root-cause established at the wellhead",
        ],
    )
    def test_root_cause_claims_are_caught_below_the_level(self, text: str) -> None:
        assert forbidden_root_cause_wording(text, CausalLevel.PROXIMATE_DRIVER)

    def test_the_permitted_disclosure_is_not_an_offence(self) -> None:
        """ "Root cause unresolved" is the wording section 18.4 asks for, not the one it forbids."""
        assert not forbidden_root_cause_wording(
            "Proximate driver identified: choke reduction. Root cause unresolved: no report says.",
            CausalLevel.PROXIMATE_DRIVER,
        )

    def test_at_the_documented_level_the_claim_is_allowed(self) -> None:
        assert not forbidden_root_cause_wording(
            "Root cause documented: planned choke reduction, per report X.",
            CausalLevel.DOCUMENTED_ROOT_CAUSE,
        )


class TestDiagnosticBundle:
    def test_a_sentinel_zero_makes_a_channel_unavailable_rather_than_zero_valued(self) -> None:
        """The whole reason section 18.2 has an availability record."""
        before = series(dt.date(2010, 1, 1), 60)
        during = series(dt.date(2010, 3, 2), 20, pressure=0.0)
        bundle = build_bundle(
            WELL, dt.date(2010, 3, 2), dt.date(2010, 3, 21), {WELL: before + during}
        )
        assert Channel.DOWNHOLE_PRESSURE in bundle.unavailable_mandatory
        pressure = bundle.comparison(Channel.DOWNHOLE_PRESSURE)
        assert pressure is not None
        assert pressure.standardised_shift is None
        assert not pressure.comparable

    def test_a_channel_that_did_not_move_is_not_a_channel_that_is_missing(self) -> None:
        before = series(dt.date(2010, 1, 1), 60)
        during = series(dt.date(2010, 3, 2), 20)
        bundle = build_bundle(
            WELL, dt.date(2010, 3, 2), dt.date(2010, 3, 21), {WELL: before + during}
        )
        assert not bundle.unavailable_mandatory

    def test_a_choke_back_shows_up_as_a_shift(self) -> None:
        before = [
            classified(dt.date(2010, 1, 1) + dt.timedelta(days=i), choke=50.0 + (i % 3))
            for i in range(60)
        ]
        during = series(dt.date(2010, 3, 2), 20, choke=30.0, oil=500.0)
        bundle = build_bundle(
            WELL, dt.date(2010, 3, 2), dt.date(2010, 3, 21), {WELL: before + during}
        )
        choke = bundle.comparison(Channel.CHOKE_SIZE)
        assert choke is not None and choke.standardised_shift is not None
        assert choke.standardised_shift < -1.0

    def test_the_offset_comparison_sees_a_field_wide_drop(self) -> None:
        other = "15/9-F-14"
        mine = series(dt.date(2010, 1, 1), 60) + series(dt.date(2010, 3, 2), 20, oil=400.0)
        theirs = series(dt.date(2010, 1, 1), 60, well=other) + series(
            dt.date(2010, 3, 2), 20, oil=300.0, well=other
        )
        bundle = build_bundle(
            WELL, dt.date(2010, 3, 2), dt.date(2010, 3, 21), {WELL: mine, other: theirs}
        )
        assert bundle.offsets.wells_also_down == (other,)
        assert bundle.offsets.field_wide


class TestTheBaseline:
    """`strongest-deviation`, fixed by section 18.6 and exempt from amendment."""

    def test_it_names_the_largest_movement(self) -> None:
        before = [
            classified(dt.date(2010, 1, 1) + dt.timedelta(days=i), choke=50.0 + (i % 3))
            for i in range(60)
        ]
        during = series(dt.date(2010, 3, 2), 20, choke=30.0)
        bundle = build_bundle(
            WELL, dt.date(2010, 3, 2), dt.date(2010, 3, 21), {WELL: before + during}
        )
        assert baseline.call(bundle).proximate_driver == "choke reduction"

    def test_it_abstains_when_nothing_moved_much(self) -> None:
        days = series(dt.date(2010, 1, 1), 60) + series(dt.date(2010, 3, 2), 20)
        bundle = build_bundle(WELL, dt.date(2010, 3, 2), dt.date(2010, 3, 21), {WELL: days})
        assert baseline.call(bundle).abstained

    def test_it_never_claims_a_documented_root_cause(self) -> None:
        """Reading nothing, it cannot reach the level that requires a document."""
        days = series(dt.date(2010, 1, 1), 60) + series(dt.date(2010, 3, 2), 20, choke=20.0)
        bundle = build_bundle(WELL, dt.date(2010, 3, 2), dt.date(2010, 3, 21), {WELL: days})
        call = baseline.call(bundle)
        assert call.root_cause == "unresolved"
        assert call.causal_level is not CausalLevel.DOCUMENTED_ROOT_CAUSE

    def test_an_unavailable_channel_is_skipped_and_recorded_never_imputed(self) -> None:
        days = series(dt.date(2010, 1, 1), 60) + series(dt.date(2010, 3, 2), 20, pressure=0.0)
        bundle = build_bundle(WELL, dt.date(2010, 3, 2), dt.date(2010, 3, 21), {WELL: days})
        assert Channel.DOWNHOLE_PRESSURE in baseline.call(bundle).skipped_channels


class TestStageOrderIsTheBoundedAgencyCheck:
    def test_the_declared_loop_is_accepted(self) -> None:
        check_stage_order(
            [
                Stage.VALIDATE_REQUEST,
                Stage.LOAD_EXPECTATION,
                Stage.DIAGNOSTIC_BUNDLE,
                Stage.FORM_HYPOTHESES,
                Stage.RETRIEVE_EVIDENCE,
                Stage.SEEK_CONTRADICTION,
                Stage.DECIDE_CONTINUE,
                Stage.RETRIEVE_EVIDENCE,
                Stage.SEEK_CONTRADICTION,
                Stage.DECIDE_CONTINUE,
                Stage.COMPOSE_FINDING,
                Stage.VALIDATE_PROVENANCE,
            ]
        )

    @pytest.mark.parametrize(
        ("stages", "match"),
        [
            ([Stage.FORM_HYPOTHESES, Stage.VALIDATE_REQUEST], "out of order"),
            ([Stage.VALIDATE_REQUEST, Stage.VALIDATE_REQUEST], "repeats"),
            ([Stage.VALIDATE_REQUEST, Stage.RETRIEVE_EVIDENCE], "before any hypothesis"),
            (
                [Stage.FORM_HYPOTHESES, Stage.COMPOSE_FINDING, Stage.RETRIEVE_EVIDENCE],
                "after the finding",
            ),
        ],
    )
    def test_a_sequence_the_controller_could_not_produce_is_refused(
        self, stages: list[Stage], match: str
    ) -> None:
        with pytest.raises(TraceError, match=match):
            check_stage_order(stages)

    def test_an_empty_trace_records_nothing(self) -> None:
        with pytest.raises(TraceError, match="records nothing"):
            check_stage_order([])


def _bundle_and_index(
    *, pressure: float | None = 230.0, choke_during: float = 30.0, comment: str = "Choke reduced."
) -> tuple[DiagnosticBundle, BM25Index, dict[str, str], Episode]:
    before = [
        classified(dt.date(2010, 1, 1) + dt.timedelta(days=i), choke=50.0 + (i % 3))
        for i in range(60)
    ]
    during = series(dt.date(2010, 3, 2), 20, choke=choke_during, oil=400.0, pressure=pressure)
    bundle = build_bundle(WELL, dt.date(2010, 3, 2), dt.date(2010, 3, 21), {WELL: before + during})
    chunk = Chunk(
        chunk_id="npt_1",
        text=comment,
        well=WELL,
        wellbore=WELL,
        source_document="d.xml",
        report_date="2010-03-05",
        activity_code="interruption -- other",
    )
    return (
        bundle,
        BM25Index([chunk]),
        {"npt_1": comment},
        episode_of(dt.date(2010, 3, 2), dt.date(2010, 3, 21)),
    )


class TestTheControllerStaysInsideItsBounds:
    def test_an_investigation_passes_the_gate_and_replays_exactly(self) -> None:
        bundle, index, documents, episode = _bundle_and_index()
        ledger = FactLedger()
        result = investigate(
            episode,
            bundle,
            index,
            documents,
            ledger,
            oil_price_usd_per_sm3=400.0,
        )
        assert result.finding is not None
        assert check(result.finding, ledger, documents).passed

        replayed = investigate(
            episode,
            bundle,
            index,
            documents,
            FactLedger(),
            judgement=ReplayJudgement(result.trace),
            oil_price_usd_per_sm3=400.0,
        )
        assert replayed.finding == result.finding

    def test_the_trace_records_only_the_declared_stages(self) -> None:
        bundle, index, documents, episode = _bundle_and_index()
        result = investigate(episode, bundle, index, documents, FactLedger())
        check_stage_order(list(result.trace.stages))
        assert result.trace.stages[0] is Stage.VALIDATE_REQUEST
        assert result.trace.stages[-1] is Stage.VALIDATE_PROVENANCE

    def test_a_trace_survives_a_round_trip_through_disk(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        bundle, index, documents, episode = _bundle_and_index()
        result = investigate(episode, bundle, index, documents, FactLedger())
        path = tmp_path / "t.json"
        result.trace.write(path)
        assert Trace.read(path) == result.trace

    def test_a_missing_channel_stops_the_investigation_rather_than_being_worked_around(
        self,
    ) -> None:
        """Section 18.3 condition 3, on the shape four real episodes actually have."""
        bundle, index, documents, episode = _bundle_and_index(pressure=0.0, choke_during=50.0)
        result = investigate(episode, bundle, index, documents, FactLedger())
        assert result.finding is not None
        assert result.finding.stop_reason is StopReason.MANDATORY_EVIDENCE_UNAVAILABLE
        assert result.finding.curtailed
        assert Channel.DOWNHOLE_PRESSURE in result.finding.unavailable_mandatory

    def test_a_step_budget_of_one_is_reported_not_hidden(self) -> None:
        bundle, index, documents, episode = _bundle_and_index()
        result = investigate(
            episode,
            bundle,
            index,
            documents,
            FactLedger(),
            budget=Budget(max_steps=1),
        )
        assert result.finding is not None
        assert result.finding.stop_reason is StopReason.STEP_BUDGET_REACHED
        assert result.finding.curtailed
        assert "curtailed" in result.finding.narrative

    def test_a_pressure_hypothesis_is_unresolved_when_there_is_no_pressure(self) -> None:
        bundle, _, _, _ = _bundle_and_index(pressure=0.0)
        pressure = next(h for h in form_hypotheses(bundle) if h.hypothesis_id == "H-pressure")
        assert pressure.status is HypothesisStatus.UNRESOLVED
        assert pressure.missing_evidence

    def test_the_rule_based_role_never_reaches_a_documented_root_cause(self) -> None:
        """Reaching that level needs reading, which is what a model-backed role would add."""
        bundle, index, documents, episode = _bundle_and_index()
        result = investigate(
            episode,
            bundle,
            index,
            documents,
            FactLedger(),
            judgement=RuleBasedJudgement(),
        )
        assert result.finding is not None
        assert result.finding.highest_level is not CausalLevel.DOCUMENTED_ROOT_CAUSE


class TestTheProvenanceGateBlocksEachWayAFindingCanBeUnfounded:
    def finding(self, ledger: FactLedger, **over: object) -> Finding:
        actual = ledger.record("a", 1.0, "Sm3", source="s")
        expected = ledger.record("e", 2.0, "Sm3/d", source="s")
        shortfall = ledger.record("s", 3.0, "Sm3", source="s")
        base: dict[str, object] = {
            "finding_id": "f1",
            "well": WELL,
            "episode_onset": "2010-03-02",
            "episode_offset": "2010-03-21",
            "actual_volume_fact_id": actual.id,
            "expected_volume_fact_id": expected.id,
            "shortfall_fact_id": shortfall.id,
            "verdict": Verdict.INSUFFICIENT_EVIDENCE,
            "hypotheses": (),
            "availability": (),
            "stop_reason": StopReason.EVIDENCE_EXHAUSTED,
            "curtailed": False,
            "steps_used": 9,
            "narrative": f"Well {WELL} produced below expectation.",
            "missing_evidence": (),
            "what_would_change_the_conclusion": ("anything",),
            "recommended_next_check": "look",
            "investigator_version": "investigator-v0",
        }
        base.update(over)
        return Finding(**base)

    def test_a_clean_finding_passes(self) -> None:
        ledger = FactLedger()
        assert check(self.finding(ledger), ledger, {}).passed

    def test_a_fact_that_is_not_in_the_ledger_blocks_it(self) -> None:
        ledger = FactLedger()
        result = check(self.finding(ledger, shortfall_fact_id="fact_999"), ledger, {})
        assert not result.passed
        assert any(v.rule == "fact_not_in_ledger" for v in result.violations)

    def test_a_span_that_is_not_verbatim_blocks_it(self) -> None:
        ledger = FactLedger()
        hypothesis = Hypothesis(
            hypothesis_id="H",
            description="d",
            causal_level=CausalLevel.PROXIMATE_DRIVER,
            status=HypothesisStatus.PLAUSIBLE,
            supporting=(
                EvidenceRef(
                    kind=EvidenceKind.DOCUMENT_SPAN,
                    document="d.xml",
                    event_id="npt_1",
                    span="a paraphrase",
                ),
            ),
        )
        result = check(
            self.finding(ledger, hypotheses=(hypothesis,)), ledger, {"npt_1": "the text"}
        )
        assert any(v.rule == "span_not_verbatim" for v in result.violations)

    def test_a_cited_document_that_was_not_supplied_blocks_it(self) -> None:
        """A gate that passes what it cannot see is not a gate."""
        ledger = FactLedger()
        hypothesis = Hypothesis(
            hypothesis_id="H",
            description="d",
            causal_level=CausalLevel.PROXIMATE_DRIVER,
            status=HypothesisStatus.PLAUSIBLE,
            supporting=(
                EvidenceRef(
                    kind=EvidenceKind.DOCUMENT_SPAN,
                    document="d.xml",
                    event_id="absent",
                    span="x",
                ),
            ),
        )
        result = check(self.finding(ledger, hypotheses=(hypothesis,)), ledger, {})
        assert any(v.rule == "document_not_available" for v in result.violations)

    def test_a_number_in_the_narrative_with_no_fact_behind_it_blocks_it(self) -> None:
        """The leak the other rules miss: impeccable citations beside an invented figure."""
        ledger = FactLedger()
        result = check(self.finding(ledger, narrative="The well lost 4321 Sm3 of oil."), ledger, {})
        assert any(v.rule == "unsourced_number_in_narrative" for v in result.violations)

    def test_a_well_name_is_not_read_as_a_number(self) -> None:
        ledger = FactLedger()
        assert check(
            self.finding(ledger, narrative=f"Well {WELL} underperformed."), ledger, {}
        ).passed

    def test_supporting_a_hypothesis_whose_channel_is_missing_blocks_it(self) -> None:
        """On this dataset not hypothetical: four development episodes have no downhole pressure."""
        ledger = FactLedger()
        hypothesis = Hypothesis(
            hypothesis_id="H-pressure",
            description="d",
            causal_level=CausalLevel.SUPPORTED_MECHANISM,
            status=HypothesisStatus.SUPPORTED,
            required_channels=(Channel.DOWNHOLE_PRESSURE,),
        )
        availability = (
            ChannelAvailability(
                channel=Channel.DOWNHOLE_PRESSURE, unit="bar", days=20, usable=0, mandatory=True
            ),
        )
        result = check(
            self.finding(ledger, hypotheses=(hypothesis,), availability=availability), ledger, {}
        )
        assert any(v.rule == "supported_without_mandatory_channel" for v in result.violations)

    def test_root_cause_wording_above_the_level_blocks_it(self) -> None:
        ledger = FactLedger()
        hypothesis = Hypothesis(
            hypothesis_id="H",
            description="d",
            causal_level=CausalLevel.PROXIMATE_DRIVER,
            status=HypothesisStatus.SUPPORTED,
        )
        result = check(
            self.finding(
                ledger,
                hypotheses=(hypothesis,),
                narrative="Root cause identified: the choke.",
                verdict=Verdict.SUPPORTED_EXPLANATION,
            ),
            ledger,
            {},
        )
        assert any(v.rule == "root_cause_wording_above_level" for v in result.violations)

    def test_a_curtailed_run_that_does_not_say_so_blocks_it(self) -> None:
        ledger = FactLedger()
        result = check(
            self.finding(ledger, stop_reason=StopReason.STEP_BUDGET_REACHED, curtailed=False),
            ledger,
            {},
        )
        assert any(v.rule == "stop_reason_not_declared" for v in result.violations)
