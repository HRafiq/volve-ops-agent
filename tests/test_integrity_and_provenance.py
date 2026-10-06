"""Section 14.3's two pass marks, and the label provenance that section 17 hangs on.

Both are checks on checks: the integrity harness has to find a parser defect that the parser
itself would not report, and the provenance field has to make the section 17.2 suspension
structural rather than something a reader is trusted to remember.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable
from pathlib import Path

import pytest

from test_extraction import activity, report
from volve_ops.extraction.adjudication import (
    ADJUDICATION_SIZE,
    CONTESTED,
    draw_adjudication_sample,
)
from volve_ops.extraction.integrity import check_reports
from volve_ops.extraction.labels import LabelFileError, join_to_events, read_label_file
from volve_ops.extraction.npt import CauseLabel as C
from volve_ops.extraction.npt import NPTEvent, extract_from_report
from volve_ops.extraction.scoring import (
    ConditionResult,
    LabelledEvent,
    LabelSource,
    approach_is_selected,
    evaluate,
    selection_permitted,
)

PUBLISHED = Path(__file__).resolve().parents[1] / "labels" / "development_pass1.jsonl"


class TestDetectionExactness:
    """Pass mark 1: every qualifying block becomes exactly one event, and nothing else does."""

    def test_a_clean_extraction_passes_both_marks(self, tmp_path: Path) -> None:
        path = report(tmp_path, activity() + activity(code="drilling -- drill", state="ok"))
        events = list(extract_from_report(path))
        result = check_reports([path], events)
        assert result.qualifying_blocks == 1
        assert result.events_checked == 1
        assert result.detection_exact
        assert result.duration_exact
        assert result.passed

    def test_a_dropped_qualifying_block_is_caught(self, tmp_path: Path) -> None:
        """The defect the harness exists for: a block the parser should have emitted and did not."""
        path = report(
            tmp_path,
            activity(start="2010-06-01T04:00:00+02:00", end="2010-06-01T05:00:00+02:00")
            + activity(start="2010-06-01T07:00:00+02:00", end="2010-06-01T08:00:00+02:00"),
        )
        events = list(extract_from_report(path))
        assert len(events) == 2
        result = check_reports([path], events[:1])
        assert not result.detection_exact
        assert [f.kind for f in result.findings] == ["missing_event"]

    def test_an_event_for_a_block_that_does_not_qualify_is_caught(self, tmp_path: Path) -> None:
        productive = report(
            tmp_path,
            activity(code="drilling -- drill", state="ok"),
            name="15_9_F_12_2010_06_01.xml",
        )
        qualifying = report(tmp_path, activity(), name="15_9_F_11_2010_06_02.xml")
        smuggled = next(iter(extract_from_report(qualifying))).model_copy(
            update={"source_document": productive.name}
        )
        result = check_reports([productive], [smuggled])
        assert not result.detection_exact
        assert any(f.kind == "unexpected_event" for f in result.findings)

    def test_a_duplicated_event_id_is_caught(self, tmp_path: Path) -> None:
        """Two distinct events sharing an id, which the (source, start, code, index) scheme allows
        across separate drillReport elements in one file."""
        path = report(tmp_path, activity())
        event = next(iter(extract_from_report(path)))
        twin = event.model_copy(update={"start_time": event.start_time + dt.timedelta(hours=3)})
        assert twin.event_id == event.event_id
        assert twin.start_time != event.start_time
        result = check_reports([path], [event, twin])
        assert not result.detection_exact
        assert any(f.kind == "duplicate_event_id" for f in result.findings)

    def test_a_document_with_no_event_is_still_checked(self, tmp_path: Path) -> None:
        """A report skipped for being empty hides exactly the defect this mark looks for."""
        path = report(tmp_path, activity())
        result = check_reports([path], [])
        assert result.documents == 1
        assert result.qualifying_blocks == 1
        assert not result.detection_exact


class TestDurationExactness:
    """Pass mark 2: the stored duration is the block's own timestamps, to within a minute."""

    def test_a_wrong_duration_is_caught(self, tmp_path: Path) -> None:
        path = report(tmp_path, activity())
        event = next(iter(extract_from_report(path)))
        result = check_reports([path], [event.model_copy(update={"duration_hours": 9.0})])
        assert not result.duration_exact
        assert [f.kind for f in result.findings] == ["duration_mismatch"]

    def test_a_sub_minute_difference_is_within_tolerance(self, tmp_path: Path) -> None:
        path = report(tmp_path, activity())
        event = next(iter(extract_from_report(path)))
        nudged = event.duration_hours + 0.9 / 60.0
        assert check_reports([path], [event.model_copy(update={"duration_hours": nudged})]).passed


class TestSelectionIsWithheldFromMachineLabels:
    """Protocol section 17.2, enforced in code rather than in prose."""

    def labels(self, source: LabelSource) -> list[LabelledEvent]:
        return [
            LabelledEvent(
                event_id=str(n),
                cause=C.EQUIPMENT_FAILURE if n % 2 else C.NOT_STATED,
                label_source=source,
                comment="pump failed",
            )
            for n in range(12)
        ]

    def test_expert_labels_permit_selection(self) -> None:
        assert selection_permitted(self.labels(LabelSource.EXPERT))

    def test_machine_labels_do_not(self) -> None:
        assert not selection_permitted(self.labels(LabelSource.MACHINE_ASSISTED))

    def test_one_machine_label_is_enough_to_withhold_it(self) -> None:
        mixed = self.labels(LabelSource.EXPERT)
        mixed[-1] = mixed[-1].model_copy(update={"label_source": LabelSource.MACHINE_ASSISTED})
        assert not selection_permitted(mixed)

    def test_evaluate_marks_the_first_two_conditions_as_reporting_only(self) -> None:
        labelled = self.labels(LabelSource.MACHINE_ASSISTED)
        spans = {
            e.event_id: ("pump failed" if e.cause is not C.NOT_STATED else None) for e in labelled
        }
        perfect = {e.event_id: e.cause for e in labelled}
        forced = {e.event_id: C.EQUIPMENT_FAILURE for e in labelled}
        useless = {e.event_id: C.RIG_SERVICE for e in labelled}

        results = evaluate(
            labelled,
            lambda i: perfect[i],
            lambda i: forced[i],
            spans,
            {"baseline": lambda i: useless[i]},
        )
        assert [r.gates for r in results] == [False, False, True, True]
        # The figures are still computed, and still say what they said.
        assert results[0].passed
        assert "machine-assisted" in results[0].detail
        assert "machine-assisted" in results[1].detail
        # The span gate keeps its authority, because it does not depend on the cause being right.
        assert results[2].gates and results[2].passed

    def test_expert_labels_let_all_four_gate(self) -> None:
        labelled = self.labels(LabelSource.EXPERT)
        spans = {
            e.event_id: ("pump failed" if e.cause is not C.NOT_STATED else None) for e in labelled
        }
        perfect = {e.event_id: e.cause for e in labelled}
        results = evaluate(
            labelled,
            lambda i: perfect[i],
            lambda i: C.EQUIPMENT_FAILURE,
            spans,
            {"baseline": lambda i: C.RIG_SERVICE},
        )
        assert all(r.gates for r in results)


class TestTheLabelFileRefusesWhatTheGuideForbids:
    def rows(self, **over: object) -> list[dict[str, object]]:
        row: dict[str, object] = {
            "event_id": "a",
            "cause": "equipment_failure",
            "evidence_span": "pump 1 failed",
            "labeller_pass": 1,
            "label_source": "machine_assisted",
        }
        row.update(over)
        return [row]

    def test_a_missing_provenance_is_refused_on_read(self, tmp_path: Path) -> None:
        row = self.rows()[0]
        del row["label_source"]
        path = tmp_path / "l.jsonl"
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        with pytest.raises(LabelFileError, match="missing"):
            read_label_file(path)

    def test_a_missing_provenance_is_refused_on_join(self) -> None:
        from test_labels import event

        row = self.rows()[0]
        del row["label_source"]
        with pytest.raises(LabelFileError, match="label_source"):
            join_to_events([row], [event("a")])

    def test_an_unknown_provenance_is_refused(self) -> None:
        from test_labels import event

        with pytest.raises(LabelFileError, match="not a label source"):
            join_to_events(self.rows(label_source="vibes"), [event("a")])

    def test_not_stated_may_not_carry_a_span(self) -> None:
        from test_labels import event

        with pytest.raises(LabelFileError, match="not_stated but a span is cited"):
            join_to_events(self.rows(cause="not_stated"), [event("a")])

    def test_a_cause_without_a_span_is_refused(self) -> None:
        from test_labels import event

        with pytest.raises(LabelFileError, match="carries no span"):
            join_to_events(self.rows(evidence_span=None), [event("a")])

    def test_a_span_that_is_not_in_the_comment_is_refused(self) -> None:
        from test_labels import event

        with pytest.raises(LabelFileError, match="not a substring"):
            join_to_events(self.rows(evidence_span="pump 2 failed"), [event("a")])


class TestThePublishedLabelSet:
    """The committed label file, checked for the invariants that do not need the event store.

    The store is not committed, so a span cannot be matched against its comment here. What can be
    checked is everything the guide fixes about the rows themselves, which is what would drift if
    the file were ever edited by hand.
    """

    def rows(self) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for line in PUBLISHED.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_it_is_the_sample_size_the_protocol_fixed(self) -> None:
        rows = self.rows()
        assert len(rows) == 135
        assert len({r["event_id"] for r in rows}) == len(rows)

    def test_every_row_declares_machine_provenance(self) -> None:
        for row in self.rows():
            assert row["label_source"] == LabelSource.MACHINE_ASSISTED.value
            assert row["labeller"]
            assert row["labeller_pass"] == 1

    def test_a_cause_has_a_span_and_not_stated_has_none(self) -> None:
        for row in self.rows():
            if row["cause"] == C.NOT_STATED.value:
                assert row["evidence_span"] is None, row["event_id"]
            else:
                assert row["evidence_span"], row["event_id"]

    def test_every_cause_is_in_the_taxonomy_and_every_row_names_its_rule(self) -> None:
        causes = {c.value for c in C}
        for row in self.rows():
            assert row["cause"] in causes, row["event_id"]
            assert row["applied_rule"], row["event_id"]

    def test_the_contested_rows_are_isolable(self) -> None:
        """The rows precedence rule 1 takes from rule 3 carry their own tag, so a reader who
        disagrees with that resolution can find them without re-deriving which they were."""
        rows = self.rows()
        contested = [r for r in rows if r["applied_rule"] == "P1-unreachable"]
        assert len(contested) == 10
        assert all(r["cause"] == C.NOT_STATED.value for r in contested)
        # Rule 1 makes both classes unreachable in this sample, which is the finding.
        assert not any(
            r["cause"] in {C.EQUIPMENT_MAINTENANCE.value, C.RIG_SERVICE.value} for r in rows
        )

    def test_other_stays_under_the_fraction_that_would_condemn_the_taxonomy(self) -> None:
        """The guide revises the taxonomy rather than stretching `other` past a fifth."""
        rows = self.rows()
        other = sum(1 for r in rows if r["cause"] == C.OTHER.value)
        assert other / len(rows) < 0.20, f"{other}/{len(rows)}"


class TestSelectionHasOnePlaceToLive:
    """Finding from review: `gates` alone is advisory, and a hand-written conjunction over it
    turns a four-condition bar into a two-condition one on a machine-assisted set."""

    def condition(self, *, passed: bool, gates: bool) -> ConditionResult:
        return ConditionResult(name="c", passed=passed, detail="", gates=gates)

    def test_all_four_passing_and_gating_selects(self) -> None:
        assert approach_is_selected([self.condition(passed=True, gates=True)] * 4)

    def test_a_suspended_condition_blocks_selection_however_well_the_rest_score(self) -> None:
        results = [
            self.condition(passed=True, gates=False),
            self.condition(passed=True, gates=False),
            self.condition(passed=True, gates=True),
            self.condition(passed=True, gates=True),
        ]
        assert not approach_is_selected(results)
        # The aggregation a caller would write by hand is the one this exists to replace.
        assert all(r.passed for r in results if r.gates)

    def test_a_failing_gating_condition_blocks_selection(self) -> None:
        assert not approach_is_selected(
            [self.condition(passed=True, gates=True), self.condition(passed=False, gates=True)]
        )

    def test_no_conditions_is_not_a_pass(self) -> None:
        assert not approach_is_selected([])

    def test_the_published_label_set_cannot_select_anything(self) -> None:
        labelled = [
            LabelledEvent(
                event_id=str(n),
                cause=C.EQUIPMENT_FAILURE if n % 2 else C.NOT_STATED,
                label_source=LabelSource.MACHINE_ASSISTED,
                comment="pump failed",
            )
            for n in range(12)
        ]
        spans = {
            e.event_id: ("pump failed" if e.cause is not C.NOT_STATED else None) for e in labelled
        }
        perfect = {e.event_id: e.cause for e in labelled}
        results = evaluate(
            labelled,
            lambda i: perfect[i],
            lambda i: C.EQUIPMENT_FAILURE,
            spans,
            {"baseline": lambda i: C.RIG_SERVICE},
        )
        assert all(r.passed for r in results)
        assert not approach_is_selected(results)


class TestTheAdjudicationDraw:
    """Protocol section 17.4's subsample: fixed size, stratified on the contested classes, blind."""

    def labels(self) -> dict[str, C]:
        contested = [C.EQUIPMENT_FAILURE, C.EQUIPMENT_MAINTENANCE, C.RIG_SERVICE]
        out: dict[str, C] = {}
        for n in range(60):
            out[f"e{n:03d}"] = contested[n % 3] if n < 30 else C.NOT_STATED
        return out

    def events(self, ids: Iterable[str]) -> list[NPTEvent]:
        return [
            NPTEvent(
                event_id=i,
                well="15/9-F-12",
                wellbore="15/9-F-12",
                source_document="d.xml",
                report_date=dt.date(2010, 6, 1),
                start_time=dt.datetime(2010, 6, 1, 4),
                end_time=dt.datetime(2010, 6, 1, 6),
                duration_hours=2.0,
                activity_code="interruption -- repair",
                category="interruption",
                subcategory="repair",
                state="ok",
                state_detail="equipment failure",
                comment=f"comment for {i}",
            )
            for i in ids
        ]

    def test_it_draws_the_fixed_size_half_from_the_contested_classes(self) -> None:
        labels = self.labels()
        draw = draw_adjudication_sample(labels, self.events(labels))
        assert draw.size == ADJUDICATION_SIZE == 40
        assert draw.from_contested_classes == 20
        assert draw.from_the_rest == 20
        assert len(set(draw.event_ids)) == 40
        drawn_contested = sum(1 for i in draw.event_ids if labels[i] in CONTESTED)
        assert drawn_contested == 20

    def test_the_draw_is_reproducible(self) -> None:
        labels = self.labels()
        events = self.events(labels)
        assert (
            draw_adjudication_sample(labels, events).event_ids
            == draw_adjudication_sample(labels, events).event_ids
        )

    def test_a_different_seed_draws_differently(self) -> None:
        labels = self.labels()
        events = self.events(labels)
        other = draw_adjudication_sample(labels, events, seed=1)
        assert set(other.event_ids) != set(draw_adjudication_sample(labels, events).event_ids)

    def test_a_short_stratum_is_made_up_from_the_other(self) -> None:
        """40 is the size the protocol fixed; quietly returning fewer widens the interval."""
        labels = {f"e{n:03d}": (C.EQUIPMENT_FAILURE if n < 5 else C.NOT_STATED) for n in range(60)}
        draw = draw_adjudication_sample(labels, self.events(labels))
        assert draw.size == 40
        assert draw.from_contested_classes == 5
        assert draw.from_the_rest == 35

    def test_the_worksheet_carries_no_label_and_no_rule(self) -> None:
        """An adjudicator shown the answer measures agreement with a suggestion."""
        labels = self.labels()
        item = draw_adjudication_sample(labels, self.events(labels)).items[0]
        fields = set(item.model_dump())
        assert not fields & {"cause", "label_source", "evidence_span", "applied_rule", "labeller"}
        # Exactly protocol section 14.2's permitted set. `wellbore` is absent on purpose: the
        # machine labelling pass saw it, which was a deviation, and repeating it here would hand
        # the adjudicator the era of the well.
        assert fields == {
            "position",
            "event_id",
            "start_time",
            "end_time",
            "duration_hours",
            "activity_code",
            "state",
            "state_detail",
            "comment",
        }
        assert "wellbore" not in fields

    def test_a_label_with_no_event_is_an_error_rather_than_a_smaller_draw(self) -> None:
        labels = self.labels()
        with pytest.raises(ValueError, match="drifted apart"):
            draw_adjudication_sample(labels, self.events(list(labels)[:10]))

    def test_the_published_set_draws_a_full_blind_subsample(self) -> None:
        rows = [
            json.loads(line)
            for line in PUBLISHED.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        labels = {str(r["event_id"]): C(str(r["cause"])) for r in rows}
        draw = draw_adjudication_sample(labels, self.events(labels))
        assert draw.size == 40
        assert draw.from_contested_classes == 20
        assert draw.eligible == 135
