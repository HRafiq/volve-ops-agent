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
    MIN_READINGS_FOR_A_CHANNEL,
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
from volve_ops.investigation.validator import CitableDocument, check, unsourced_numbers
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
    *,
    pressure: float | None = 230.0,
    choke_during: float = 30.0,
    comment: str = "Choke reduced.",
    document_well: str = WELL,
    report_date: str = "2010-03-05",
) -> tuple[DiagnosticBundle, BM25Index, dict[str, CitableDocument], Episode]:
    before = [
        classified(dt.date(2010, 1, 1) + dt.timedelta(days=i), choke=50.0 + 6.0 * (i % 3))
        for i in range(60)
    ]
    during = series(dt.date(2010, 3, 2), 20, choke=choke_during, oil=400.0, pressure=pressure)
    bundle = build_bundle(WELL, dt.date(2010, 3, 2), dt.date(2010, 3, 21), {WELL: before + during})
    chunk = Chunk(
        chunk_id="npt_1",
        text=comment,
        well=document_well,
        wellbore=document_well,
        source_document="d.xml",
        report_date=report_date,
        activity_code="interruption -- other",
    )
    documents = {
        "npt_1": CitableDocument(
            event_id="npt_1",
            source_document="d.xml",
            well=document_well,
            report_date=dt.date.fromisoformat(report_date),
            text=comment,
        )
    }
    return (
        bundle,
        BM25Index([chunk]),
        documents,
        episode_of(dt.date(2010, 3, 2), dt.date(2010, 3, 21)),
    )


class CostlyJudgement(RuleBasedJudgement):
    """A role that charges for its judgement, so the cost stop condition is reachable."""

    name = "costly"
    cost_per_call_usd = 1.0


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
        """Section 18.3 condition 3, on the shape three real episodes actually have."""
        bundle, index, documents, episode = _bundle_and_index(pressure=0.0, choke_during=50.5)
        result = investigate(episode, bundle, index, documents, FactLedger())
        assert result.finding is not None
        assert result.finding.stop_reason is StopReason.MANDATORY_EVIDENCE_UNAVAILABLE
        assert result.finding.curtailed
        assert Channel.DOWNHOLE_PRESSURE in result.finding.unavailable_mandatory

    def test_a_cost_budget_is_reachable_and_reported(self) -> None:
        """Review found this stop condition listed everywhere and settable nowhere."""
        bundle, index, documents, episode = _bundle_and_index()
        result = investigate(
            episode,
            bundle,
            index,
            documents,
            FactLedger(),
            judgement=CostlyJudgement(),
            budget=Budget(max_cost_usd=0.5),
        )
        assert result.finding is not None
        assert result.finding.stop_reason is StopReason.COST_BUDGET_REACHED
        assert result.finding.curtailed
        assert result.trace.cost_usd > 0.0

    def test_retrieval_asks_about_supported_hypotheses_not_only_plausible_ones(self) -> None:
        """The defect review found: the hypothesis a finding rests on was never put to documents.

        A document stating a reason lifts a supported hypothesis to `documented_root_cause`, so if
        supported hypotheses are never queried the top causal level is unreachable in practice.
        """
        bundle, index, documents, episode = _bundle_and_index(
            comment="Closed in well to prepare for handover."
        )
        result = investigate(episode, bundle, index, documents, FactLedger())
        assert result.finding is not None
        assert result.finding.highest_level is CausalLevel.DOCUMENTED_ROOT_CAUSE
        assert sum(len(h.supporting) for h in result.finding.hypotheses) > 0

    def test_more_than_one_evidence_pass_can_run(self) -> None:
        """`another_pass` used to return False whenever a pass found nothing, so every run was one
        pass long and the pass budget was dead."""
        bundle, index, documents, episode = _bundle_and_index()
        result = investigate(episode, bundle, index, documents, FactLedger())
        passes = sum(1 for s in result.trace.steps if s.stage is Stage.RETRIEVE_EVIDENCE)
        assert passes >= 2

    def test_a_channel_with_one_reading_is_not_an_available_channel(self) -> None:
        """`usable > 0` let a single reading in twenty days suppress the missing-data disclosure."""
        assert MIN_READINGS_FOR_A_CHANNEL == 3
        thin = ChannelAvailability(
            channel=Channel.DOWNHOLE_PRESSURE, unit="bar", days=20, usable=1, mandatory=True
        )
        assert not thin.available

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

    def test_a_document_that_says_only_what_was_done_does_not_reach_the_documented_level(
        self,
    ) -> None:
        """The level needs a stated reason, not merely a cited span."""
        bundle, index, documents, episode = _bundle_and_index(comment="Closed in well.")
        result = investigate(episode, bundle, index, documents, FactLedger())
        assert result.finding is not None
        assert result.finding.highest_level is not CausalLevel.DOCUMENTED_ROOT_CAUSE


class TestTheProvenanceGateBlocksEachWayAFindingCanBeUnfounded:
    """Every rule, including the four that independent review proved the first version did not hold.

    The gate is the product. A finding that looks sound and is unfounded is the failure this whole
    layer exists to prevent, so each test below is a reconstruction of a way through.
    """

    def document(
        self,
        *,
        text: str = "Choke reduced to protect the separator.",
        well: str = WELL,
        source: str = "d.xml",
        report_date: dt.date = dt.date(2010, 3, 5),
    ) -> dict[str, CitableDocument]:
        return {
            "npt_1": CitableDocument(
                event_id="npt_1",
                source_document=source,
                well=well,
                report_date=report_date,
                text=text,
            )
        }

    def citing(self, **over: object) -> Hypothesis:
        ref: dict[str, object] = {
            "kind": EvidenceKind.DOCUMENT_SPAN,
            "document": "d.xml",
            "event_id": "npt_1",
            "span": "Choke reduced",
        }
        ref.update(over)
        return Hypothesis(
            hypothesis_id="H",
            description="d",
            causal_level=CausalLevel.PROXIMATE_DRIVER,
            status=HypothesisStatus.PLAUSIBLE,
            supporting=(EvidenceRef(**ref),),
        )

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
        result = check(self.finding(ledger, hypotheses=(self.citing(),)), ledger, self.document())
        assert result.passed, result.violations

    def test_a_fact_that_is_not_in_the_ledger_blocks_it(self) -> None:
        ledger = FactLedger()
        result = check(self.finding(ledger, shortfall_fact_id="fact_999"), ledger, {})
        assert any(v.rule == "fact_not_in_ledger" for v in result.violations)

    def test_a_span_that_is_not_verbatim_blocks_it(self) -> None:
        ledger = FactLedger()
        result = check(
            self.finding(ledger, hypotheses=(self.citing(span="a paraphrase"),)),
            ledger,
            self.document(),
        )
        assert any(v.rule == "span_not_verbatim" for v in result.violations)

    def test_a_cited_document_that_was_not_supplied_blocks_it(self) -> None:
        """A gate that passes what it cannot see is not a gate."""
        ledger = FactLedger()
        result = check(
            self.finding(ledger, hypotheses=(self.citing(event_id="absent"),)), ledger, {}
        )
        assert any(v.rule == "document_not_available" for v in result.violations)

    def test_a_fabricated_filename_beside_a_real_span_blocks_it(self) -> None:
        """Review's hole (c): the document name was read only to format an error message."""
        ledger = FactLedger()
        result = check(
            self.finding(ledger, hypotheses=(self.citing(document="MADE_UP_REPORT.pdf"),)),
            ledger,
            self.document(),
        )
        assert any(v.rule == "document_name_wrong" for v in result.violations)

    def test_a_span_borrowed_from_another_well_blocks_it(self) -> None:
        """Review's hole (d). Comments repeat across wells, so the span really is present."""
        ledger = FactLedger()
        result = check(
            self.finding(ledger, hypotheses=(self.citing(),)),
            ledger,
            self.document(well="15/9-F-14"),
        )
        assert any(v.rule == "citation_from_another_well" for v in result.violations)

    def test_a_span_from_years_away_blocks_it(self) -> None:
        ledger = FactLedger()
        result = check(
            self.finding(ledger, hypotheses=(self.citing(),)),
            ledger,
            self.document(report_date=dt.date(2007, 6, 1)),
        )
        assert any(v.rule == "citation_outside_the_window" for v in result.violations)

    def test_a_wellbore_citation_matches_a_finding_on_its_well(self) -> None:
        """`15/9-F-15 D` and `15/9-F-15` are one well; a citation must not be rejected for it."""
        ledger = FactLedger()
        result = check(
            self.finding(ledger, well="15/9-F-15 D", hypotheses=(self.citing(),)),
            ledger,
            self.document(well="15/9-F-15"),
        )
        assert not any(v.rule == "citation_from_another_well" for v in result.violations)

    @pytest.mark.parametrize(
        ("prose", "expected"),
        [
            ("Production fell by 4200 Sm3 over 31 days.", ["4200", "31"]),
            ("Downhole pressure fell from 310 bar to 180 bar in 2011.", ["310", "180"]),
            ("The choke closed from 62 to 14 of 100 steps.", ["62", "14", "100"]),
            ("The well lost 88000 Sm3 (12%).", ["88000"]),
            (f"Well {WELL} lost 4321 Sm3.", ["4321"]),
            (f"Well {WELL} produced below expectation over the episode window.", []),
            ("Drilled in 2011 and again in 2016.", []),
            ("Read the operations log around 2010-03-02.", []),
            ("Between 2010-03-02 and 2010-03-21 it lost 500 Sm3.", ["500"]),
            ("Water cut rose to 37%.", []),
        ],
    )
    def test_the_number_rule_exempts_the_token_not_its_neighbourhood(
        self, prose: str, expected: list[str]
    ) -> None:
        """Review's hole (b): proximity to `day`, a year or `%` waved most sentences through."""
        assert unsourced_numbers(prose) == expected

    def test_the_well_name_strip_does_not_swallow_the_sentence(self) -> None:
        """Review's hole (a), and the reason it went unnoticed: the old test could not fail.

        Asserting that a narrative passes the gate is satisfied both by stripping the well name and
        by deleting the whole sentence. This asserts what survives.
        """
        assert unsourced_numbers(f"Well {WELL} lost 4321 Sm3 over the window.") == ["4321"]
        assert unsourced_numbers("Well 15/9-19 BT2 lost 99 Sm3.") == ["99"]
        assert unsourced_numbers("Well 15/9-F-1 C lost 7 Sm3.") == ["7"]

    def test_an_invented_figure_anywhere_in_the_published_prose_blocks_it(self) -> None:
        """Not the narrative alone: every prose field is published just as widely."""
        ledger = FactLedger()
        for field in ("recommended_next_check", "narrative"):
            result = check(self.finding(ledger, **{field: "It lost 4321 Sm3."}), ledger, {})
            assert any(v.rule == "unsourced_number_in_prose" for v in result.violations), field

    def test_supporting_a_hypothesis_whose_channel_is_missing_blocks_it(self) -> None:
        """Not hypothetical here: three development episodes have no downhole pressure."""
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
                narrative="The underlying reason was the operator's decision.",
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

    def test_the_exploit_review_built_is_refused(self) -> None:
        """One finding carrying all four holes at once, which the first gate passed clean."""
        ledger = FactLedger()
        hypothesis = self.citing(document="TOTALLY_MADE_UP_REPORT.pdf")
        result = check(
            self.finding(
                ledger,
                hypotheses=(hypothesis,),
                narrative=f"Well {WELL} lost 4200 Sm3 over 31 days. The root cause was the choke.",
            ),
            ledger,
            self.document(well="15/9-F-14", report_date=dt.date(2007, 6, 1)),
        )
        rules = {v.rule for v in result.violations}
        assert {
            "document_name_wrong",
            "citation_from_another_well",
            "citation_outside_the_window",
            "unsourced_number_in_prose",
            "root_cause_wording_above_level",
        } <= rules

    def test_a_finding_at_the_documented_level_may_not_disclaim_it(self) -> None:
        """The mirror of the wording check: understating evidence the project did have.

        Review's run produced a finding at `documented_root_cause` whose narrative still read "Root
        cause unresolved", because the narrative generator only knew two of the three levels.
        """
        ledger = FactLedger()
        hypothesis = Hypothesis(
            hypothesis_id="H",
            description="d",
            causal_level=CausalLevel.DOCUMENTED_ROOT_CAUSE,
            status=HypothesisStatus.SUPPORTED,
        )
        result = check(
            self.finding(
                ledger,
                hypotheses=(hypothesis,),
                verdict=Verdict.SUPPORTED_EXPLANATION,
                narrative="Mechanism supported. Root cause unresolved: no report says why.",
            ),
            ledger,
            {},
        )
        assert any(v.rule == "documented_level_disclaims_itself" for v in result.violations)
