"""Protocol section 22.4 marks 11 and 12: the System Health workspace.

Mark 11 is checked against the assembled payload with the same gate every other screen's figures
go through. Mark 12 is checked structurally, because the way this screen is most likely to lie is
by publishing a delta it cannot compute, and an empty column reads as no change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from volve_ops.console import assemble, gates
from volve_ops.console.payloads import ComparisonRow
from volve_ops.console.sources import Sourced
from volve_ops.console.store import RunStore

CACHE = Path("data/cache")


@pytest.fixture(scope="module")
def health():  # type: ignore[no-untyped-def]
    if not (CACHE / "security_run.json").exists() or not (CACHE / "ablation_run.json").exists():
        pytest.skip(
            "no section 22 manifests; run scripts/run_security_checks.py and "
            "scripts/run_ablations.py"
        )
    return assemble.system_health(RunStore())


class TestMark11EveryFigureResolves:
    def test_every_health_figure_resolves_to_a_manifest(self, health) -> None:  # type: ignore[no-untyped-def]
        store = RunStore()
        facts: set[str] = set()
        for path in (CACHE / "investigations").glob("*.facts.json"):
            facts |= {str(f["id"]) for f in json.loads(path.read_text(encoding="utf-8"))}
        outcome = gates.figures_resolve(
            {"system_health": health},
            store.health_manifests(),
            fact_ids=frozenset(facts),
            artifacts=CACHE / "investigations",
        )
        assert outcome.passed, list(outcome.detail)
        assert outcome.examined > 20, "the gate examined too few sources to mean anything"

    def test_the_ablation_table_counts_its_own_rows(self, health) -> None:  # type: ignore[no-untyped-def]
        table = health.expectation_ablation
        assert table.rows_mismatch() is None
        assert table.declared_rows() == len(table.rows)

    def test_the_ablation_table_declares_its_derived_columns(self, health) -> None:  # type: ignore[no-untyped-def]
        # Both columns are figures this project computed, so both are results and amendment 10's
        # third bound requires them declared.
        assert health.expectation_ablation.derived_columns == {"episodes_opened", "wape"}


class TestMark12NoDeltaItCannotCompute:
    def test_no_comparison_row_invents_a_delta(self, health) -> None:  # type: ignore[no-untyped-def]
        for row in health.comparison:
            if row.delta is None:
                assert row.unavailable_because.strip(), row.metric
            else:
                assert row.previous is not None, row.metric

    def test_a_delta_without_a_reason_is_unconstructible(self) -> None:
        with pytest.raises(ValueError, match="no delta and no reason"):
            ComparisonRow(metric="x", current=Sourced(value=1.0, source="security.passed", unit=""))

    def test_a_delta_without_a_previous_value_is_unconstructible(self) -> None:
        with pytest.raises(ValueError, match="no previous value"):
            ComparisonRow(
                metric="x",
                current=Sourced(value=1.0, source="security.passed", unit=""),
                delta=Sourced(value=0.0, source="security.passed", unit=""),
            )

    def test_a_well_formed_comparison_is_accepted(self) -> None:
        row = ComparisonRow(
            metric="x",
            current=Sourced(value=2.0, source="security.passed", unit=""),
            previous=Sourced(value=1.0, source="security.passed", unit=""),
            delta=Sourced(value=1.0, source="security.passed", unit=""),
        )
        assert row.delta is not None


class TestTheScreenReportsWhatItCannotDo:
    def test_the_three_vacuous_invariants_are_listed_with_reasons(self, health) -> None:  # type: ignore[no-untyped-def]
        assert len(health.vacuous_invariants) == 3
        for invariant in health.vacuous_invariants:
            assert len(invariant.reason) > 50

    def test_the_vacuous_invariants_are_not_in_the_counts(self, health) -> None:  # type: ignore[no-untyped-def]
        # The display must not undo what the report structure prevents.
        labels = {row.label for row in health.injection}
        assert not any("vacuous" in label.lower() for label in labels)

    def test_not_applicable_protections_carry_their_reason(self, health) -> None:  # type: ignore[no-untyped-def]
        assert health.not_applicable
        for item in health.not_applicable:
            assert len(item.reason) > 20

    def test_the_calibration_ablation_runs_and_states_its_limits(self, health) -> None:  # type: ignore[no-untyped-def]
        """It was declared not applicable and is now run; amendment 12 records why.

        What matters on the screen is that the result arrives with what it cannot show. A spread
        between an evidence-derived score and a flat prior says the score carries information; it
        says nothing about whether any band was right, and four of five features are circular.
        """
        assert health.calibration, "the calibration ablation reports no rows"
        assert "no ground truth" in health.calibration_note
        assert len(health.circular_features) == 4

    def test_the_flat_prior_is_a_real_comparison_arm(self, health) -> None:  # type: ignore[no-untyped-def]
        labels = {row.label for row in health.calibration}
        assert any("Flat-prior" in label for label in labels)
        assert any("spread" in label for label in labels)
        # Bands must be published per band rather than as one number, or a screen cannot show
        # that the evidence score spreads findings where a flat prior cannot.
        assert sum("Evidence-derived band" in label for label in labels) >= 2

    def test_the_retrieval_note_reports_its_population(self, health) -> None:  # type: ignore[no-untyped-def]
        assert "minority" in health.retrieval_note or "ADR 0008" in health.retrieval_note

    def test_every_experiment_named_is_a_file_that_exists(self, health) -> None:  # type: ignore[no-untyped-def]
        # Section 22.10 asks for experiment ids that reproduce. An id naming nothing reproduces
        # nothing, and a reader cannot tell the difference from the screen.
        for entry in health.experiments:
            for part in entry.split(" + "):
                assert Path(part.strip()).exists(), part
