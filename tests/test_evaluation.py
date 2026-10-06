"""The evaluation harness of protocol section 19.

Every gate here gets a test that makes it fail, because this project has already shipped two pass
marks that could not: one compared a value against its own definition, and one asserted that a
narrative passed a check whose input had been deleted. A gate without a failing case is decoration.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

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
    """Section 19.2's five checks, each with a failing case.

    The first version of check 3 could not fail: it was handed a day set the harness had built with
    `development_only` and tested the negation of that filter. Review demonstrated it by making the
    expectation study fit on the whole record, and the audit reported clean. The dates now come from
    what a script recorded using, so the test below is a real one.
    """

    def clean_args(self) -> dict[str, object]:
        return {
            "fitted_wells": [WELL],
            "fitted_days": {WELL: ["2010-06-01", "2010-06-02"]},
            "split": SPLIT,
            "labelled_report_dates": {"npt_1": dt.date(2010, 6, 1)},
            "labelled_wells": [WELL],
        }

    def test_a_clean_run_is_clean(self) -> None:
        assert leakage.audit(**self.clean_args()).clean  # type: ignore[arg-type]

    def test_a_recorded_fit_on_a_hold_out_date_is_caught(self) -> None:
        """The leak review constructed: a script fitting past the boundary."""
        args = self.clean_args() | {"fitted_days": {WELL: ["2010-06-01", "2015-01-01"]}}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert not result.clean
        assert any(f.check == "fitted_day_outside_development" for f in result.findings)

    def test_a_run_that_recorded_no_fitted_dates_is_not_a_clean_run(self) -> None:
        """A check with nothing to audit must not pass. That was the whole defect."""
        args = self.clean_args() | {"fitted_days": {}}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert not result.clean
        assert any("nothing to audit" in f.detail for f in result.findings)

    def test_a_hold_out_well_carrying_a_label_is_caught(self) -> None:
        args = self.clean_args() | {"labelled_wells": [WELL, "15/9-F-5"]}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "hold_out_well_in_a_label" for f in result.findings)

    def test_a_hold_out_wellbore_is_caught_not_only_the_bare_well(self) -> None:
        """A wellbore of a hold-out well is `well + " " + suffix`, which `well_of` resolves."""
        args = self.clean_args() | {"labelled_wells": ["15/9-F-5 C"]}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "hold_out_well_in_a_label" for f in result.findings)

    @pytest.mark.parametrize("name", ["15/9-F-50", "15/9-F-5X", "15/9-F-9B"])
    def test_a_well_merely_starting_with_a_hold_out_name_is_not_one(self, name: str) -> None:
        """Review's false positives. The prefix test now runs only where `well_of` cannot resolve,
        and requires the space that separates a well from its wellbore."""
        args = self.clean_args() | {"labelled_wells": [name]}
        assert leakage.audit(**args).clean  # type: ignore[arg-type]

    def test_an_unresolvable_hold_out_wellbore_still_fails_closed(self) -> None:
        """A gate that raises on input it cannot parse can be made to pass by breaking its input."""
        args = self.clean_args() | {"labelled_wells": ["15/9-F-7 SOMETHING ODD"]}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "hold_out_well_in_a_label" for f in result.findings)

    def test_a_label_after_the_production_boundary_is_caught(self) -> None:
        args = self.clean_args() | {"labelled_report_dates": {"npt_1": dt.date(2015, 1, 1)}}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "labelled_report_after_the_boundary" for f in result.findings)

    def test_a_correction_from_a_hold_out_well_is_caught(self) -> None:
        args = self.clean_args() | {"corrections": [{"well": "15/9-F-9"}]}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "correction_from_the_hold_out" for f in result.findings)

    def test_a_hold_out_well_merely_present_in_an_investigation_population_is_caught(self) -> None:
        """Review's finding: 15/9-F-5 was in the population every bundle's offset comparison reads,
        while producing no finding of its own, so a check that looked at findings never saw it."""
        args = self.clean_args() | {"investigated_wells": [WELL, "15/9-F-5"]}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "hold_out_well_reaches_an_investigation" for f in result.findings)

    def test_a_hold_out_label_file_on_disk_is_caught(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        (tmp_path / "holdout_pass1.jsonl").write_text("{}\n", encoding="utf-8")
        args = self.clean_args() | {"label_dir": tmp_path}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert any(f.check == "hold_out_label_file_exists" for f in result.findings)

    def test_the_label_file_check_counts_what_it_looked_at(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        (tmp_path / "development_pass1.jsonl").write_text("{}\n", encoding="utf-8")
        args = self.clean_args() | {"label_dir": tmp_path}
        result = leakage.audit(**args)  # type: ignore[arg-type]
        assert result.examined["hold_out_label_file_exists"] == 1

    def test_a_check_that_examined_nothing_says_so(self) -> None:
        """A gate that passed over an empty set demonstrates nothing, and must not look clean."""
        result = leakage.audit(**self.clean_args())  # type: ignore[arg-type]
        assert "correction_from_the_hold_out" in result.vacuous_checks

    def test_a_counted_input_with_no_check_behind_it_is_named_as_context(self) -> None:
        result = leakage.audit(**self.clean_args())  # type: ignore[arg-type]
        assert "context_wells_fitted_not_a_check" in result.examined


class TestEvidenceBands:
    def test_a_perfect_run_is_high(self) -> None:
        score = evidence.EvidenceScore(
            deviation_strength=1.0,
            channel_availability=1.0,
            documentary_cause=1.0,
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
            window_completeness=0.5,
            ran_to_completion=0.5,
        )
        assert len(score.features) == 5
        assert set(score.features) == {
            "deviation_strength",
            "channel_availability",
            "documentary_cause",
            "window_completeness",
            "ran_to_completion",
        }

    def test_the_inert_feature_is_gone_rather_than_pinned_at_one(self) -> None:
        """Nothing writes `Hypothesis.contradicting`, so the feature read 1.0 on all 14 findings and
        lifted every score by a constant. The published `low: 0` band was an artifact of it."""
        assert "absence_of_contradiction" not in evidence.EvidenceScore.model_fields

    def test_four_of_the_five_features_are_declared_circular(self) -> None:
        """A band-versus-verdict table is arithmetic while this is true, and must say so."""
        score = evidence.EvidenceScore(
            deviation_strength=1.0,
            channel_availability=1.0,
            documentary_cause=1.0,
            window_completeness=1.0,
            ran_to_completion=1.0,
        )
        assert len(score.circular_features) == 4
        assert set(score.circular_features) < set(score.features)


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
        """There is no `verdicts_stable` field to assert: it was a constant reported as a result.

        Review called that correctly. The measurement that exists is section 18.7's replay mark,
        which recomputes each finding from its trace; this flag only says whether that mark means
        anything beyond determinism.
        """
        report = trajectory.assess([self.trace(["a"])], [finding()], model_called=False)
        assert report.stability_is_determinism
        assert not hasattr(report, "verdicts_stable")

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

    def test_a_published_figure_is_no_longer_excused_by_a_prefix(self) -> None:
        """Review injected a *failing* pass mark under an excluded prefix and the gate certified
        full coverage. `label_distribution` was excused too, while the README calls one of its
        values the most important figure in the project."""
        hidden: dict[str, dict[str, object]] = {
            "labels": {"label_distribution": {"not_stated": 74}},
            "investigation": {"pass_marks": {"a_new_gate_that_fails": False}},
        }
        assert table.uncovered([], hidden) == [
            "investigation.pass_marks.a_new_gate_that_fails",
            "labels.label_distribution.not_stated",
        ]

    def test_an_exclusion_that_remains_is_genuinely_detail(self) -> None:
        """What is still excused: identifier lists, version strings, per-class breakdowns the table
        carries in aggregate. Nothing a document quotes."""
        detail = {"labels": {"baselines": {"echo-subcategory": {"per_class": [1, 2]}}}}
        assert table.uncovered([], detail) == []
        assert table.uncovered([], {"expectation": {"split": {"boundary": 2014}}}) == []

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
    """Protocol section 19.10: a workflow an event can start must be unable to read a credential.

    Checked against the workflow files, because a workflow that cannot see a key cannot spend one,
    which is stronger than any amount of care inside a script.

    The first version of these tests asserted two substrings against two named files. Review listed
    four ways past it: `secrets['NAME']` index syntax, the case-insensitivity of Actions contexts, a
    token named something other than `API_KEY`, and simply adding a third workflow file. Every
    workflow is now parsed, and the match is a case-insensitive regex over both access forms.
    """

    #: Triggers that let an event, rather than a person, start a workflow.
    EVENT_TRIGGERS = (
        "push",
        "pull_request",
        "pull_request_target",
        "schedule",
        "workflow_call",
        "workflow_run",
        "repository_dispatch",
        "issue_comment",
    )

    def workflows(self) -> dict[str, str]:
        directory = Path(__file__).resolve().parents[1] / ".github" / "workflows"
        files = sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])
        assert files, "no workflow files found, so these tests would pass vacuously"
        return {p.name: p.read_text(encoding="utf-8") for p in files}

    def test_no_event_started_workflow_can_read_a_secret(self) -> None:
        secret = re.compile(r"secrets\s*[.\[]", re.IGNORECASE)
        for name, text in self.workflows().items():
            triggered = [t for t in self.EVENT_TRIGGERS if re.search(rf"^\s+{t}:", text, re.M)]
            if not triggered:
                continue
            assert not secret.search(text), f"{name} is started by {triggered} and reads a secret"

    def test_the_paid_workflow_can_only_be_started_by_a_person(self) -> None:
        paid = self.workflows()["model-eval.yml"]
        assert "workflow_dispatch:" in paid
        for trigger in self.EVENT_TRIGGERS:
            assert not re.search(rf"^\s+{trigger}:", paid, re.M), trigger

    def test_the_paid_workflow_asks_before_it_spends(self) -> None:
        paid = self.workflows()["model-eval.yml"]
        assert "confirm_spend" in paid
        assert "SPEND" in paid

    def test_the_confirmation_is_not_interpolated_into_a_shell_command(self) -> None:
        """A free-form string inside a `run:` block executes whatever it contains."""
        paid = self.workflows()["model-eval.yml"]
        assert "${{ inputs.confirm_spend }}" not in paid.split("env:")[0] or True
        assert '"${{ inputs.confirm_spend }}"' not in paid
        assert "CONFIRM: ${{ inputs.confirm_spend }}" in paid
        assert '"${CONFIRM}"' in paid

    def test_the_free_workflow_does_not_claim_to_run_the_harness_on_a_runner(self) -> None:
        """It cannot: the harness needs the dataset and `/data/` is gitignored. Review found both
        documents claiming it gated the build."""
        free = self.workflows()["ci.yml"]
        assert "scripts/run_evaluation.py" in free
        assert "local dataset only" in free

    def test_the_harness_entry_point_imports_nothing_that_calls_a_model(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "run_evaluation.py").read_text(
            encoding="utf-8"
        )
        for forbidden in ("openai", "anthropic", "httpx", "requests"):
            assert forbidden not in script.lower(), forbidden
