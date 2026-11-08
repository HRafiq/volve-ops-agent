"""Protocol section 22.6 and mark 8: seven ways to be wrong about where a figure came from.

Mark 8 requires each class to be **stopped at the gate**. A test that builds an invalid finding
and asserts the constructor refused it has tested the constructor, so every experiment here
builds something the type system accepts, hands it to the real publication gate, and records
which rule fired.

Six of the seven are investigation-gate classes. Class 3 is not: a `Finding` carries fact ids and
no figures, so nothing in it can contradict a record. The figures live in the console payloads,
which is where amendment 11 found the defect, and that is where class 3 is checked.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from volve_ops.investigation.schemas import CausalLevel, EvidenceKind, EvidenceRef
from volve_ops.investigation.validator import CitableDocument
from volve_ops.security import suite
from volve_ops.security.provenance_failures import (
    FAILURE_CLASSES,
    Contradiction,
    contradictions_in_console,
    figures_contradicting_their_records,
    run_at_the_gate,
)

WELL = "15/9-F-12"
REPORT = suite.FIXTURE_REPORT_NAME


@pytest.fixture(scope="module")
def arm() -> suite.InvestigationArm:
    """A real, clean investigation to break one thing at a time in."""
    return suite.InvestigationArm(suite.BENIGN_COMMENT)


def _documents() -> dict[str, CitableDocument]:
    return {
        "npt_1": CitableDocument(
            event_id="npt_1",
            source_document=REPORT,
            well=WELL,
            report_date=dt.date(2010, 3, 5),
            text=suite.BENIGN_COMMENT,
        )
    }


def _class(number: int):  # type: ignore[no-untyped-def]
    return next(f for f in FAILURE_CLASSES if f.number == number)


class TestTheInvestigationGateBlocksSixOfThem:
    def test_1_a_derived_figure_with_no_lineage(self, arm: suite.InvestigationArm) -> None:
        """A derived fact whose input is no longer in the ledger: a chain reaching no measurement.

        The first version emptied the ledger entirely, so every anchor was missing,
        `fact_not_in_ledger` fired, and the test asserted only `outcome.blocked`. That is class 2
        wearing class 1's name: `broken_lineage`, the rule this class exists to demonstrate, never
        fired at all. Independent review caught it.

        Building it needs a derived fact, and this run's three anchors are all measured, which is
        itself worth knowing: nothing the finding anchors to is computed from anything else, so
        class 1 cannot arise from the current controller and has to be constructed.
        """
        from volve_ops.provenance.facts import FactLedger

        ledger = FactLedger()
        measured = ledger.record("episode_actual_volume", 1000.0, "Sm3", source="workbook")
        derived = ledger.derive(
            "episode_cumulative_rate_shortfall",
            "Sm3",
            formula="actual minus expected",
            inputs=[measured],
            compute=lambda a: a * 0.5,
        )
        # The input is removed; the derived fact keeps citing it. The chain now reaches nothing.
        del ledger._facts[measured.id]

        broken = arm.finding.model_copy(
            update={
                "actual_volume_fact_id": derived.id,
                "expected_volume_fact_id": derived.id,
                "shortfall_fact_id": derived.id,
                "shortfall_value_fact_id": None,
            }
        )
        outcome = run_at_the_gate(_class(1), broken, ledger, _documents())
        assert outcome.blocked, outcome.detail
        assert outcome.blocked_by_the_expected_rule, (outcome.rules_fired, outcome.detail)

    def test_2_a_source_that_does_not_resolve(self, arm: suite.InvestigationArm) -> None:
        broken = arm.finding.model_copy(update={"shortfall_fact_id": "fact_999999"})
        outcome = run_at_the_gate(_class(2), broken, arm.ledger, _documents())
        assert outcome.blocked_by_the_expected_rule, outcome.detail

    def test_4_a_quote_attributed_to_the_wrong_document(self, arm: suite.InvestigationArm) -> None:
        broken = _with_evidence(
            arm,
            EvidenceRef(
                kind=EvidenceKind.DOCUMENT_SPAN,
                event_id="npt_1",
                document="a_different_report.xml",
                span=suite.BENIGN_COMMENT[:20],
            ),
        )
        outcome = run_at_the_gate(_class(4), broken, arm.ledger, _documents())
        assert outcome.blocked_by_the_expected_rule, outcome.detail

    def test_5_a_cited_event_that_does_not_exist(self, arm: suite.InvestigationArm) -> None:
        broken = _with_evidence(
            arm,
            EvidenceRef(
                kind=EvidenceKind.DOCUMENT_SPAN,
                event_id="npt_does_not_exist",
                document=REPORT,
                span=suite.BENIGN_COMMENT[:20],
            ),
        )
        outcome = run_at_the_gate(_class(5), broken, arm.ledger, _documents())
        assert outcome.blocked_by_the_expected_rule, outcome.detail

    def test_6_evidence_from_outside_the_episode_window(self, arm: suite.InvestigationArm) -> None:
        far_off = {
            "npt_1": CitableDocument(
                event_id="npt_1",
                source_document=REPORT,
                well=WELL,
                report_date=dt.date(2009, 1, 1),
                text=suite.BENIGN_COMMENT,
            )
        }
        broken = _with_evidence(
            arm,
            EvidenceRef(
                kind=EvidenceKind.DOCUMENT_SPAN,
                event_id="npt_1",
                document=REPORT,
                span=suite.BENIGN_COMMENT[:20],
            ),
        )
        outcome = run_at_the_gate(_class(6), broken, arm.ledger, far_off)
        assert outcome.blocked_by_the_expected_rule, outcome.detail

    def test_7_a_documented_level_that_disclaims_its_document(
        self, arm: suite.InvestigationArm
    ) -> None:
        first, *rest = arm.finding.hypotheses
        claimed = (
            first.model_copy(
                update={"causal_level": CausalLevel.DOCUMENTED_ROOT_CAUSE, "supporting": ()}
            ),
            *rest,
        )
        broken = arm.finding.model_copy(update={"hypotheses": claimed})
        outcome = run_at_the_gate(_class(7), broken, arm.ledger, _documents())
        assert outcome.blocked, outcome.detail

    def test_a_clean_finding_passes_the_gate(self, arm: suite.InvestigationArm) -> None:
        # Without this every test above would pass against a gate that refuses everything.
        outcome = run_at_the_gate(_class(2), arm.finding, arm.ledger, _documents())
        assert outcome.blocked is False, outcome.detail


def _with_evidence(arm: suite.InvestigationArm, ref: EvidenceRef):  # type: ignore[no-untyped-def]
    first, *rest = arm.finding.hypotheses
    return arm.finding.model_copy(
        update={"hypotheses": (first.model_copy(update={"supporting": (ref,)}), *rest)}
    )


class TestClassThreeAtTheConsole:
    """The class amendment 11 recorded: a source that resolves to a different number."""

    def test_a_figure_contradicting_its_record_is_found(self) -> None:
        from volve_ops.console.sources import Sourced

        payload = {"shortfall": Sourced(value=4351.41, source="fact_000002", unit="Sm3")}
        found = figures_contradicting_their_records({"detail": payload}, {"fact_000002": 3052.735})
        assert len(found) == 1
        assert found[0].published == 4351.41
        assert found[0].recorded == 3052.735

    def test_a_figure_matching_its_record_is_not_flagged(self) -> None:
        from volve_ops.console.sources import Sourced

        payload = {"shortfall": Sourced(value=3052.735, source="fact_000002", unit="Sm3")}
        assert figures_contradicting_their_records({"d": payload}, {"fact_000002": 3052.735}) == ()

    def test_float_slack_is_allowed_and_display_rounding_is_not(self) -> None:
        from volve_ops.console.sources import Sourced

        recorded = 3052.735
        slack = {"x": Sourced(value=recorded + 1e-12, source="f", unit="Sm3")}
        assert figures_contradicting_their_records({"d": slack}, {"f": recorded}) == ()
        # Section 21.1 requires the unrounded value in the payload, so a rounded figure is a
        # violation rather than a tolerance question.
        rounded = {"x": Sourced(value=3052.7, source="f", unit="Sm3")}
        assert len(figures_contradicting_their_records({"d": rounded}, {"f": recorded})) == 1

    def test_a_source_that_is_not_a_fact_id_is_left_to_mark_one(self) -> None:
        from volve_ops.console.sources import Sourced

        payload = {"x": Sourced(value=1.0, source="rule:21.5", unit="")}
        assert figures_contradicting_their_records({"d": payload}, {"fact_000001": 9.0}) == ()

    def test_the_console_publishes_no_contradiction(self) -> None:
        """The run that matters. Skipped where the cache is absent, never silently passed."""
        from volve_ops.console.store import RunStore

        if not Path("data/cache/investigation_run.json").exists():
            pytest.skip("no cached run; this check needs the published artifacts")
        result = contradictions_in_console(RunStore())
        assert result.contradictions == (), [str(c) for c in result.contradictions]
        # The denominator, because zero contradictions over zero figures is not a clean result.
        assert result.compared > 100, result.compared

    def test_the_scoping_trap_is_real(self) -> None:
        """Fact ids restart per episode, so an unscoped map compares unrelated things.

        Pinned as a test because the first run of this check did exactly this and reported 183
        contradictions that were all artifacts of the lookup. The console was right.
        """
        from volve_ops.console.sources import Sourced

        episode_a = {"x": Sourced(value=3391.25, source="fact_000001", unit="Sm3")}
        a_facts = {"fact_000001": 3391.25}
        b_facts = {"fact_000001": 597.13}
        assert figures_contradicting_their_records({"a": episode_a}, a_facts) == ()
        assert len(figures_contradicting_their_records({"a": episode_a}, b_facts)) == 1


class TestEveryClassIsAccountedFor:
    def test_all_seven_classes_are_declared(self) -> None:
        assert {f.number for f in FAILURE_CLASSES} == set(range(1, 8))

    def test_each_class_names_the_rule_that_must_fire(self) -> None:
        for failure in FAILURE_CLASSES:
            assert failure.expected_rule, f"class {failure.number} names no rule"

    def test_a_contradiction_prints_both_numbers(self) -> None:
        line = str(
            Contradiction(
                payload="detail",
                path="a.b",
                source="fact_000002",
                published=4351.41,
                recorded=3052.735,
            )
        )
        assert "4351.41" in line and "3052.735" in line
