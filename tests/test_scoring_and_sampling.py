"""Section 14.5's conditions and the labelling draw.

These decide whether a cause-attribution approach ships, so the ways they could be passed
without the system being good are what the tests are about.
"""

from __future__ import annotations

import datetime as dt

import pytest

from volve_ops.extraction.npt import CauseLabel as C
from volve_ops.extraction.npt import NPTEvent
from volve_ops.extraction.sampling import (
    HOLD_OUT_WELLS,
    draw_sample,
    is_development,
    is_hold_out,
)
from volve_ops.extraction.scoring import (
    LabelledEvent,
    condition_abstention,
    condition_relative_margin,
    condition_spans_are_verbatim,
    score_macro,
)


def event(
    event_id: str, well: str = "15/9-F-12", sub: str = "repair", date: str = "2010-06-01"
) -> NPTEvent:
    y, m, d = (int(x) for x in date.split("-"))
    return NPTEvent(
        event_id=event_id,
        well=well,
        wellbore=well,
        source_document="d.xml",
        report_date=dt.date(y, m, d),
        start_time=dt.datetime(y, m, d, 4),
        end_time=dt.datetime(y, m, d, 6),
        duration_hours=2.0,
        activity_code=f"interruption -- {sub}",
        category="interruption",
        subcategory=sub,
        state="ok",
        state_detail="",
        comment="Mud pump failed.",
    )


class TestMacroScore:
    def test_a_perfect_prediction_scores_one(self) -> None:
        gold = [C.EQUIPMENT_FAILURE] * 6 + [C.HOLE_PROBLEM] * 6
        assert score_macro(gold, list(gold)).macro_f1 == pytest.approx(1.0)

    def test_predicting_one_class_everywhere_cannot_score_well(self) -> None:
        """The attack macro-F1 is chosen to resist: not_stated is the majority class."""
        gold = [C.NOT_STATED] * 30 + [C.EQUIPMENT_FAILURE] * 10 + [C.HOLE_PROBLEM] * 10
        assert score_macro(gold, [C.NOT_STATED] * 50).macro_f1 < 0.4

    def test_a_class_below_the_support_floor_is_reported_but_not_averaged(self) -> None:
        gold = [C.EQUIPMENT_FAILURE] * 10 + [C.WELL_CONTROL] * 2
        result = score_macro(gold, list(gold))
        assert result.classes_in_average == 1
        assert [c.label for c in result.excluded] == [C.WELL_CONTROL]
        assert result.excluded[0].support == 2

    def test_an_unobserved_class_is_not_scored_zero(self) -> None:
        """Scoring an absent class as a failure measures the sampling, not the system."""
        gold = [C.EQUIPMENT_FAILURE] * 10
        result = score_macro(gold, list(gold))
        assert {c.label for c in result.per_class} == {C.EQUIPMENT_FAILURE}
        assert result.macro_f1 == pytest.approx(1.0)

    def test_mismatched_lengths_are_refused(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            score_macro([C.NOT_STATED], [C.NOT_STATED, C.OTHER])


class TestRelativeMargin:
    def test_a_candidate_must_beat_the_better_of_the_baselines(self) -> None:
        gold = [C.EQUIPMENT_FAILURE] * 10 + [C.HOLE_PROBLEM] * 10
        candidate = list(gold)
        weak = [C.NOT_STATED] * 20
        strong = [C.EQUIPMENT_FAILURE] * 10 + [C.NOT_STATED] * 10
        result, best = condition_relative_margin(gold, candidate, {"weak": weak, "strong": strong})
        assert best == "strong"
        assert result.passed

    def test_tying_the_better_baseline_fails(self) -> None:
        gold = [C.EQUIPMENT_FAILURE] * 10 + [C.HOLE_PROBLEM] * 10
        same = [C.EQUIPMENT_FAILURE] * 10 + [C.NOT_STATED] * 10
        result, _ = condition_relative_margin(gold, list(same), {"a": list(same)})
        assert not result.passed


class TestSpanGate:
    def test_a_verbatim_span_passes(self) -> None:
        labelled = [
            LabelledEvent(
                event_id="a",
                cause=C.EQUIPMENT_FAILURE,
                comment="Mud pump 1 failed, changed liners.",
            )
        ]
        result = condition_spans_are_verbatim(labelled, {"a": "pump 1 failed"})
        assert result.passed

    def test_one_fabricated_span_fails_the_gate(self) -> None:
        """A cited span that is not in the source is a fabricated citation, and one is too many."""
        labelled = [
            LabelledEvent(event_id="a", cause=C.EQUIPMENT_FAILURE, comment="Mud pump 1 failed."),
            LabelledEvent(event_id="b", cause=C.HOLE_PROBLEM, comment="Stuck pipe."),
        ]
        result = condition_spans_are_verbatim(labelled, {"a": "pump 1 failed", "b": "losses"})
        assert not result.passed
        assert "fabricated" in result.detail

    def test_a_paraphrase_is_not_verbatim(self) -> None:
        labelled = [
            LabelledEvent(event_id="a", cause=C.EQUIPMENT_FAILURE, comment="Mud pump 1 failed.")
        ]
        assert not condition_spans_are_verbatim(labelled, {"a": "the mud pump broke"}).passed


class TestAbstention:
    @staticmethod
    def _gold() -> list[C]:
        return [C.EQUIPMENT_FAILURE] * 10 + [C.NOT_STATED] * 10

    def test_abstaining_on_all_but_one_event_does_not_pass(self) -> None:
        """Without a coverage floor, maximum selectivity is a perfect score."""
        candidate = [C.EQUIPMENT_FAILURE] + [C.NOT_STATED] * 19
        forced = [C.EQUIPMENT_FAILURE] * 10 + [C.OTHER] * 10
        result = condition_abstention(self._gold(), candidate, forced)
        assert not result.passed
        assert "coverage" in result.detail

    def test_good_coverage_with_a_real_precision_gain_passes(self) -> None:
        candidate = [C.EQUIPMENT_FAILURE] * 9 + [C.NOT_STATED] * 11
        forced = [C.EQUIPMENT_FAILURE] * 9 + [C.OTHER] * 11
        assert condition_abstention(self._gold(), candidate, forced).passed

    def test_abstention_that_buys_no_precision_fails(self) -> None:
        candidate = [C.EQUIPMENT_FAILURE] * 10 + [C.NOT_STATED] * 10
        assert not condition_abstention(self._gold(), candidate, list(candidate)).passed


class TestSampling:
    @staticmethod
    def _corpus() -> list[NPTEvent]:
        out = []
        for i in range(200):
            out.append(event(f"dev_{i:03d}", sub=["repair", "fish", "wait"][i % 3]))
        for i in range(50):
            out.append(event(f"ho_{i:03d}", well="15/9-F-7", sub="repair"))
        for i in range(20):
            out.append(event(f"late_{i:03d}", sub="repair", date="2015-01-01"))
        return out

    def test_the_draw_is_reproducible(self) -> None:
        corpus = self._corpus()
        assert draw_sample(corpus, target=30).event_ids == draw_sample(corpus, target=30).event_ids

    def test_hold_out_wells_never_enter_the_development_sample(self) -> None:
        drawn = set(draw_sample(self._corpus(), target=60).event_ids)
        assert not any(i.startswith("ho_") for i in drawn)

    def test_post_boundary_reports_are_excluded_from_labelling(self) -> None:
        """A label read from a post-boundary report is a label, not profiling."""
        drawn = set(draw_sample(self._corpus(), target=60).event_ids)
        assert not any(i.startswith("late_") for i in drawn)

    def test_the_sample_is_stratified_across_subcategories(self) -> None:
        """A proportional draw would give a rare subcategory a good chance of appearing never."""
        manifest = draw_sample(self._corpus(), target=30)
        assert set(manifest.per_subcategory) == {"repair", "fish", "wait"}
        assert min(manifest.per_subcategory.values()) >= 9

    def test_the_hold_out_split_draws_only_hold_out_wells(self) -> None:
        manifest = draw_sample(self._corpus(), split="hold-out", target=20)
        assert all(i.startswith("ho_") for i in manifest.event_ids)

    def test_the_split_rule_matches_the_protocol(self) -> None:
        assert {"15/9-F-4", "15/9-F-5", "15/9-F-7", "15/9-F-9"} == HOLD_OUT_WELLS
        assert is_hold_out(event("x", well="15/9-F-7"))
        assert is_development(event("x", well="15/9-F-12", date="2010-01-01"))
        assert not is_development(event("x", well="15/9-F-12", date="2015-01-01"))

    def test_an_unknown_split_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown split"):
            draw_sample(self._corpus(), split="whatever")
