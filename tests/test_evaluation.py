"""The evaluation harness of protocol section 19.

Every gate here gets a test that makes it fail, because this project has already shipped two pass
marks that could not: one compared a value against its own definition, and one asserted that a
narrative passed a check whose input had been deleted. A gate without a failing case is decoration.
"""

from __future__ import annotations

import datetime as dt

import pytest

from volve_ops.domain.day_class import ClassifiedDay, DayClass
from volve_ops.domain.splits import TemporalSplit
from volve_ops.evaluation import evidence, leakage, safety, table, trajectory
from volve_ops.evaluation.rows import ROWS
from volve_ops.evaluation.table import MetricRow, Status
from volve_ops.evaluation.versions import (
    ABSENT,
    REQUIRED_FIELDS,
    VersionFreeze,
    describe_model_roles,
    missing_fields,
)
from volve_ops.ingest.production import ProductionDay, WellStatus
from volve_ops.investigation.schemas import (
    CausalLevel,
    EvidenceKind,
    EvidenceRef,
    Finding,
    Hypothesis,
    HypothesisStatus,
    StopReason,
    Verdict,
)
from volve_ops.investigation.trace import Stage, Step, Trace

WELL = "15/9-F-12"
SPLIT = TemporalSplit(
    record_start=dt.date(2008, 1, 1),
    record_end=dt.date(2016, 12, 31),
    boundary=dt.date(2014, 7, 25),
    development_end=dt.date(2014, 4, 26),
)


def freeze(**over: str) -> VersionFreeze:
    base = {field: "x" for field in REQUIRED_FIELDS}
    base.update(over)
    return VersionFreeze(**base)


def classified(when: dt.date, well: str = WELL) -> ClassifiedDay:
    return ClassifiedDay(
        day=ProductionDay(
            well=well,
            production_date=when,
            on_stream_hours=24.0,
            oil_volume_sm3=900.0,
            well_status=WellStatus.PRODUCING,
            source="wb.xlsx",
        ),
        day_class=DayClass.VALID_PRODUCING,
    )


def finding(**over: object) -> Finding:
    base: dict[str, object] = {
        "finding_id": "f1",
        "well": WELL,
        "episode_onset": "2010-03-02",
        "episode_offset": "2010-03-21",
        "actual_volume_fact_id": "fact_1",
        "expected_volume_fact_id": "fact_2",
        "shortfall_fact_id": "fact_3",
        "verdict": Verdict.SUPPORTED_EXPLANATION,
        "hypotheses": (),
        "availability": (),
        "stop_reason": StopReason.EVIDENCE_EXHAUSTED,
        "curtailed": False,
        "steps_used": 9,
        "narrative": "Proximate driver identified: choke. Root cause unresolved.",
        "missing_evidence": (),
        "what_would_change_the_conclusion": ("x",),
        "recommended_next_check": "look",
        "investigator_version": "investigator-v0",
    }
    base.update(over)
    return Finding(**base)


class TestTheVersionFreeze:
    def test_a_complete_freeze_has_no_missing_fields(self) -> None:
        assert missing_fields(freeze().model_dump()) == ()

    def test_a_blank_field_is_refused_rather_than_recorded(self) -> None:
        """Section 19.1: absence is recorded as `none`, so it is a claim and not an omission."""
        with pytest.raises(ValueError, match="may not be blank"):
            freeze(commit="   ")

    def test_none_is_how_absence_is_recorded(self) -> None:
        assert freeze(correction_store_version=ABSENT).correction_store_version == ABSENT

    def test_an_omitted_field_is_detected_in_a_raw_manifest(self) -> None:
        raw = freeze().model_dump()
        del raw["label_set_version"]
        assert missing_fields(raw) == ("label_set_version",)

    def test_an_empty_string_in_a_raw_manifest_is_detected(self) -> None:
        raw = freeze().model_dump()
        raw["commit"] = ""
        assert missing_fields(raw) == ("commit",)

    def test_the_hash_reproduces_on_identical_fields(self) -> None:
        assert freeze().manifest_hash == freeze().manifest_hash

    def test_the_hash_moves_when_any_field_moves(self) -> None:
        for field in REQUIRED_FIELDS:
            assert freeze().manifest_hash != freeze(**{field: "changed"}).manifest_hash, field

    def test_no_role_bound_to_a_model_renders_as_absent(self) -> None:
        assert describe_model_roles({"JUDGE": None, "EXTRACTION": None}) == ABSENT
        assert not freeze(model_roles=ABSENT).calls_a_model

    def test_a_bound_role_is_rendered_and_the_run_counts_as_calling_a_model(self) -> None:
        rendered = describe_model_roles({"JUDGE": "some-model", "EXTRACTION": None})
        assert rendered == f"EXTRACTION={ABSENT}, JUDGE=some-model"
        assert freeze(model_roles=rendered).calls_a_model


class TestTheLeakageAudit:
    def clean_args(self) -> dict[str, object]:
        return {
            "fitted_wells": [WELL],
            "fitted_days": {WELL: [classified(dt.date(2010, 6, 1))]},
            "split": SPLIT,
            "labelled_report_dates": {"npt_1": dt.date(2010, 6, 1)},
            "labelled_wells": [WELL],
        }

    def test_a_clean_run_is_clean(self) -> None:
        result = leakage.audit(**self.clean_args())  # type: ignore[arg-type]
        assert result.clean

    def test_a_hold_out_well_carrying_a_label_is_caught(self) -> None:
        args = self.clean_args() | {"labelled_wells": [WELL, "15/9-F-5"]}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "hold_out_well_in_a_label" for f in result.findings)

    def test_a_hold_out_wellbore_is_caught_not_only_the_bare_well(self) -> None:
        """`15/9-F-5 AY1H` is a wellbore of a hold-out well; a string compare would miss it."""
        args = self.clean_args() | {"labelled_wells": ["15/9-F-5 AY1H"]}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "hold_out_well_in_a_label" for f in result.findings)

    def test_a_label_after_the_production_boundary_is_caught(self) -> None:
        args = self.clean_args() | {"labelled_report_dates": {"npt_1": dt.date(2015, 1, 1)}}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "labelled_report_after_the_boundary" for f in result.findings)

    def test_a_fitted_day_outside_development_is_caught(self) -> None:
        """The realistic failure: a filter applied one call too late rather than at the source."""
        args = self.clean_args() | {"fitted_days": {WELL: [classified(dt.date(2015, 1, 1))]}}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "fitted_day_outside_development" for f in result.findings)

    def test_a_correction_from_a_hold_out_well_is_caught(self) -> None:
        args = self.clean_args() | {"corrections": [{"well": "15/9-F-9"}]}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "correction_from_the_hold_out" for f in result.findings)

    def test_an_investigated_hold_out_well_is_caught(self) -> None:
        args = self.clean_args() | {"investigated_wells": ["15/9-F-7"]}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "hold_out_episode_investigated" for f in result.findings)

    def test_a_hold_out_label_file_on_disk_is_caught(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        (tmp_path / "hold-out_pass1.jsonl").write_text("{}\n", encoding="utf-8")
        args = self.clean_args() | {"label_dir": tmp_path}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "hold_out_label_file_exists" for f in result.findings)

    def test_a_check_that_examined_nothing_says_so(self) -> None:
        """A gate that passed over an empty set demonstrates nothing, and must not look clean."""
        result = leakage.audit(**self.clean_args())  # type: ignore[arg-type]
        assert "correction_from_the_hold_out" in result.vacuous_checks

    def test_fitting_production_on_a_drilling_hold_out_well_is_not_a_leak(self) -> None:
        """Protocol amendment 5. Section 16's hold-out is by well and governs the drilling layer;
        production is split temporally by section 10, and the layers share no data."""
        args = self.clean_args() | {
            "fitted_wells": [WELL, "15/9-F-5"],
            "fitted_days": {"15/9-F-5": [classified(dt.date(2010, 6, 1), well="15/9-F-5")]},
        }
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert result.clean


class TestEvidenceBands:
    def test_a_perfect_run_is_high(self) -> None:
        score = evidence.EvidenceScore(
            deviation_strength=1.0,
            channel_availability=1.0,
            documentary_cause=1.0,
            absence_of_contradiction=1.0,
            window_completeness=1.0,
            ran_to_completion=1.0,
        )
        assert score.score == 1.0
        assert score.band is evidence.EvidenceBand.HIGH

    def test_the_band_edges_are_the_ones_section_19_4_fixed(self) -> None:
        assert evidence.HIGH_BAND == 0.70
        assert evidence.MODERATE_BAND == 0.40

    @pytest.mark.parametrize(
        ("value", "band"),
        [
            (1.0, evidence.EvidenceBand.HIGH),
            (0.70, evidence.EvidenceBand.HIGH),
            (0.69, evidence.EvidenceBand.MODERATE),
            (0.40, evidence.EvidenceBand.MODERATE),
            (0.39, evidence.EvidenceBand.LOW),
            (0.0, evidence.EvidenceBand.LOW),
        ],
    )
    def test_each_band_is_reachable(self, value: float, band: evidence.EvidenceBand) -> None:
        score = evidence.EvidenceScore(
            deviation_strength=value,
            channel_availability=value,
            documentary_cause=value,
            absence_of_contradiction=value,
            window_completeness=value,
            ran_to_completion=value,
        )
        assert score.band is band

    def test_every_feature_is_reported_not_only_the_total(self) -> None:
        """A band alone cannot distinguish 0.5 from channels from 0.5 from a document."""
        score = evidence.EvidenceScore(
            deviation_strength=0.5,
            channel_availability=0.5,
            documentary_cause=0.5,
            absence_of_contradiction=0.5,
            window_completeness=0.5,
            ran_to_completion=0.5,
        )
        assert len(score.features) == 6
        assert set(score.features) == {
            "deviation_strength",
            "channel_availability",
            "documentary_cause",
            "absence_of_contradiction",
            "window_completeness",
            "ran_to_completion",
        }


class TestTheSafetyMetric:
    def documented(self, span: str) -> Hypothesis:
        return Hypothesis(
            hypothesis_id="H",
            description="d",
            causal_level=CausalLevel.DOCUMENTED_ROOT_CAUSE,
            status=HypothesisStatus.SUPPORTED,
            supporting=(
                EvidenceRef(
                    kind=EvidenceKind.DOCUMENT_SPAN,
                    document="d.xml",
                    event_id="npt_1",
                    span=span,
                ),
            ),
        )

    def test_a_documented_claim_citing_a_stated_reason_passes(self) -> None:
        report = safety.assess([finding(hypotheses=(self.documented("Closed in to prepare"),))])
        assert report.passed
        assert report.documented_claims == 1
        assert report.examined_anything

    def test_a_documented_claim_whose_span_states_no_reason_is_an_incident(self) -> None:
        report = safety.assess([finding(hypotheses=(self.documented("Closed in well."),))])
        assert not report.passed
        assert report.incidents[0].kind == "documented_claim_without_a_stated_reason"

    def test_a_root_cause_claim_above_its_level_is_an_incident(self) -> None:
        report = safety.assess(
            [
                finding(
                    hypotheses=(
                        Hypothesis(
                            hypothesis_id="H",
                            description="d",
                            causal_level=CausalLevel.PROXIMATE_DRIVER,
                            status=HypothesisStatus.SUPPORTED,
                        ),
                    ),
                    narrative="The root cause was the choke.",
                )
            ]
        )
        assert any(i.kind == "root_cause_claimed_above_its_level" for i in report.incidents)

    def test_a_pass_over_no_documented_claim_says_it_examined_nothing(self) -> None:
        report = safety.assess([finding()])
        assert report.passed
        assert not report.examined_anything

    def test_the_weighting_is_the_one_section_19_5_fixed(self) -> None:
        assert safety.FALSE_CLAIM_WEIGHT == 5
        assert safety.UNNECESSARY_ABSTENTION_WEIGHT == 1
        report = safety.assess([finding(hypotheses=(self.documented("Closed in well."),))])
        assert report.weighted_cost == 5

    def test_abstentions_are_counted(self) -> None:
        report = safety.assess([finding(verdict=Verdict.INSUFFICIENT_EVIDENCE), finding()])
        assert report.abstentions == 1


class TestTrajectory:
    def trace(self, queries: list[str]) -> Trace:
        steps = [
            Step(
                index=i,
                stage=Stage.RETRIEVE_EVIDENCE,
                summary="s",
                judgement_key=f"retrieval_query:{i}",
                judgement=q,
            )
            for i, q in enumerate(queries)
        ]
        return Trace(
            investigator_version="investigator-v0",
            well=WELL,
            episode_onset="2010-03-02",
            steps=tuple(steps),
        )

    def test_distinct_queries_pass(self) -> None:
        report = trajectory.assess([self.trace(["a", "b"])], [finding()])
        assert report.passed
        assert report.retrieval_passes == {"2": 1}

    def test_the_same_query_twice_is_caught(self) -> None:
        """Section 19.7's one gate: a controller that asks the same question twice has a defect."""
        report = trajectory.assess([self.trace(["a", "a"])], [finding()])
        assert not report.passed
        assert report.repeated_calls[0].times == 2

    def test_stability_is_labelled_as_determinism_while_no_model_is_called(self) -> None:
        report = trajectory.assess([self.trace(["a"])], [finding()], model_called=False)
        assert report.verdicts_stable
        assert report.stability_is_determinism

    def test_with_a_model_called_stability_is_no_longer_free(self) -> None:
        report = trajectory.assess([self.trace(["a"])], [finding()], model_called=True)
        assert not report.stability_is_determinism

    def test_cost_and_tokens_are_reported_as_zero_rather_than_omitted(self) -> None:
        report = trajectory.assess([self.trace(["a"])], [finding()])
        assert report.tokens == 0
        assert report.cost_usd == 0.0


class TestTheResultsTable:
    def test_every_declared_row_names_a_denominator(self) -> None:
        for row in ROWS:
            assert row.denominator.strip(), row.metric

    def test_every_deferred_row_says_what_would_settle_it(self) -> None:
        """A deferred row without that is an omission wearing a status."""
        for row in ROWS:
            if row.status is Status.DEFERRED:
                assert row.settled_by, row.metric

    def test_no_row_is_both_valued_and_deferred(self) -> None:
        for row in ROWS:
            if row.status is Status.DEFERRED:
                assert row.manifest is None and row.key is None, row.metric

    def test_an_unaddressed_manifest_figure_fails_the_coverage_check(self) -> None:
        """Section 19.3's gate: adding a figure without adding a row must fail."""
        manifests = {"labels": {"a_brand_new_figure": 7}}
        assert table.uncovered([], manifests) == ["labels.a_brand_new_figure"]

    def test_a_declared_prefix_excuses_a_figure(self) -> None:
        manifests = {"labels": {"label_distribution": {"not_stated": 74}}}
        assert table.uncovered([], manifests) == []

    def test_a_row_addresses_its_figure(self) -> None:
        rows = [
            MetricRow(
                layer="L",
                metric="M",
                manifest="labels",
                key="a_brand_new_figure",
                denominator="d",
                status=Status.REPORTED,
            )
        ]
        assert table.uncovered(rows, {"labels": {"a_brand_new_figure": 7}}) == []

    def test_a_boolean_counts_as_a_published_figure(self) -> None:
        """A pass mark is a result, so it needs a row like any other number."""
        assert table.uncovered([], {"labels": {"some_gate": True}}) == ["labels.some_gate"]

    def test_the_harness_can_supply_a_value_no_manifest_carries(self) -> None:
        rows = [
            MetricRow(
                layer="L",
                metric="Computed thing",
                manifest=None,
                key=None,
                denominator="d",
                status=Status.GATED,
            )
        ]
        filled = table.fill(rows, {}, {"Computed thing": True})
        assert filled[0].rendered == "pass"

    def test_a_row_with_no_value_renders_as_not_produced_rather_than_as_a_pass(self) -> None:
        rows = [
            MetricRow(
                layer="L",
                metric="M",
                manifest="labels",
                key="absent",
                denominator="d",
                status=Status.GATED,
            )
        ]
        assert table.fill(rows, {})[0].rendered == "not produced"

    def test_the_rendered_table_groups_by_layer(self) -> None:
        rendered = table.as_markdown(table.fill(ROWS, {}))
        assert "### Investigation" in rendered
        assert "### Cause labels" in rendered


class TestTheCiSplitIsStructural:
    """Protocol section 19.10: the free workflow must be unable to spend money.

    Checked against the workflow files rather than against the code, because a workflow that cannot
    see a key cannot spend one, and that is a stronger guarantee than any amount of care inside a
    script.
    """

    def workflows(self) -> dict[str, str]:
        import pathlib

        directory = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows"
        return {p.name: p.read_text(encoding="utf-8") for p in sorted(directory.glob("*.yml"))}

    def test_the_free_workflow_references_no_credential(self) -> None:
        free = self.workflows()["ci.yml"]
        assert "secrets." not in free
        assert "API_KEY" not in free

    def test_the_paid_workflow_cannot_be_started_by_an_event(self) -> None:
        """The absence of these triggers is the control, not a condition inside a job."""
        paid = self.workflows()["model-eval.yml"]
        assert "workflow_dispatch:" in paid
        for trigger in ("\n  push:", "\n  pull_request:", "\n  schedule:"):
            assert trigger not in paid, trigger

    def test_the_paid_workflow_asks_a_person_before_it_spends(self) -> None:
        paid = self.workflows()["model-eval.yml"]
        assert "confirm_spend" in paid
        assert "SPEND" in paid

    def test_the_free_workflow_runs_the_harness_and_lets_its_exit_status_gate(self) -> None:
        free = self.workflows()["ci.yml"]
        assert "scripts/run_evaluation.py" in free

    def test_the_harness_entry_point_imports_nothing_that_calls_a_model(self) -> None:
        """A cheap structural check that the free path stays free."""
        import pathlib

        script = (
            pathlib.Path(__file__).resolve().parents[1] / "scripts" / "run_evaluation.py"
        ).read_text(encoding="utf-8")
        for forbidden in ("openai", "anthropic", "httpx", "requests"):
            assert forbidden not in script.lower(), forbidden
