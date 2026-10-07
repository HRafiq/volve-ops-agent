"""The post-mortem, the lessons register and the correction store, per protocol section 20.

Every gate has a failing case, which is the habit four phases of review taught: a check written in
the
same breath as the thing it checks tends to test that thing against itself.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from volve_ops.extraction.npt import NPTEvent
from volve_ops.postmortem import corrections, recorded_time, register

DEVELOPMENT = ("15/9-F-12", "15/9-F-14", "15/9-F-15")
HOLD_OUT = "15/9-F-5"


def event(
    *,
    well: str = "15/9-F-12",
    subcategory: str = "repair",
    detail: str = "equipment failure",
    hours: float = 2.0,
    when: dt.date = dt.date(2010, 6, 1),
    comment: str = "Mud pump 1 failed, changed liners. Resumed drilling.",
    event_id: str | None = None,
) -> NPTEvent:
    return NPTEvent(
        event_id=event_id or f"npt_{well}_{when}_{subcategory}_{hours}",
        well=well,
        wellbore=well,
        source_document="d.xml",
        report_date=when,
        start_time=dt.datetime(when.year, when.month, when.day, 4),
        end_time=dt.datetime(when.year, when.month, when.day, 4) + dt.timedelta(hours=hours),
        duration_hours=hours,
        activity_code=f"interruption -- {subcategory}",
        category="interruption",
        subcategory=subcategory,
        state="ok",
        state_detail=detail,
        comment=comment,
    )


class TestRecordedTimeOverTheRealCorpus:
    """Walked from the XML, independently of the extractor. Section 20.8's verification path."""

    @pytest.fixture(scope="class")
    def walked(self) -> recorded_time.RecordedTime:
        reports = Path(__file__).resolve().parents[1] / "data" / "cache" / "ddr_xml"
        if not reports.exists():
            pytest.skip("the cached drilling reports are not present")
        return recorded_time.walk(reports)

    def test_the_categories_reconcile_to_the_block_durations(
        self, walked: recorded_time.RecordedTime
    ) -> None:
        """Section 20.2's gate, at 0.01 hours: arithmetic over one set of blocks."""
        for well in walked.wells:
            total = well.npt_hours + well.non_npt_recorded_hours
            assert abs(total - well.block_duration_hours) < 0.01, well.well

    def test_no_block_is_untimed(self, walked: recorded_time.RecordedTime) -> None:
        """A qualifying block that cannot be timed is a parser defect under section 14.3."""
        assert walked.untimed_blocks == 0

    def test_overlap_and_gaps_are_measured_not_assumed(
        self, walked: recorded_time.RecordedTime
    ) -> None:
        """Both are reported as their own figures. A tolerance wide enough to absorb them would be
        wide enough to hide an arithmetic error."""
        assert 0.0 < walked.concurrent_overlap_hours < 10.0
        assert 0.0 < walked.unclassified_gap_hours < 500.0

    def test_restricting_to_development_wells_drops_the_hold_out(
        self, walked: recorded_time.RecordedTime
    ) -> None:
        development = [
            w.well
            for w in walked.wells
            if w.well
            not in {
                "15/9-F-4",
                "15/9-F-5",
                "15/9-F-7",
                "15/9-F-9",
            }
        ]
        scope = walked.only(development)
        assert len(scope.wells) == 7
        assert scope.npt_hours < walked.npt_hours
        assert all(w.well in development for w in scope.wells)


class TestTheLessonsRegister:
    def test_a_pattern_needs_three_wells_and_a_rig_day(self) -> None:
        """Section 20.4's thresholds, fixed before the register was built."""
        assert register.MIN_WELLS == 3
        assert register.MIN_HOURS == 24.0

    def test_three_wells_and_enough_hours_recurs(self) -> None:
        events = [event(well=w, hours=10.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT)]
        built = register.build(events, wells=DEVELOPMENT)
        assert len(built.patterns) == 1
        assert built.patterns[0].wells == tuple(sorted(DEVELOPMENT))

    def test_two_wells_does_not_recur_however_many_hours(self) -> None:
        """Two wells is a coincidence. The register exists to find things worth generalising."""
        events = [
            event(well=w, hours=500.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT[:2])
        ]
        built = register.build(events, wells=DEVELOPMENT)
        assert built.patterns == ()
        assert built.excluded_patterns == 1
        assert built.excluded_hours == 1000.0

    def test_three_wells_under_a_rig_day_does_not_recur(self) -> None:
        events = [event(well=w, hours=1.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT)]
        built = register.build(events, wells=DEVELOPMENT)
        assert built.patterns == ()
        assert built.excluded_patterns == 1

    def test_a_hold_out_well_is_excluded_from_the_grouping(self) -> None:
        events = [event(well=w, hours=10.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT)]
        events.append(event(well=HOLD_OUT, hours=500.0, event_id="leak"))
        built = register.build(events, wells=DEVELOPMENT)
        assert HOLD_OUT not in built.patterns[0].wells
        assert HOLD_OUT not in built.wells
        assert built.corpus_hours == 30.0

    def test_the_representative_span_is_verbatim_in_the_comment_it_cites(self) -> None:
        events = [event(well=w, hours=10.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT)]
        pattern = register.build(events, wells=DEVELOPMENT).patterns[0]
        cited = next(e for e in events if e.event_id == pattern.representative.event_id)
        assert pattern.representative.span in cited.comment

    def test_the_representative_is_the_longest_event_not_the_first(self) -> None:
        """So the quoted span is the one that cost the most time."""
        events = [
            event(well=DEVELOPMENT[0], hours=1.0, event_id="short"),
            event(well=DEVELOPMENT[1], hours=40.0, event_id="long"),
            event(well=DEVELOPMENT[2], hours=2.0, event_id="middle"),
        ]
        pattern = register.build(events, wells=DEVELOPMENT).patterns[0]
        assert pattern.representative.event_id == "long"

    def test_the_order_is_reproducible(self) -> None:
        """Section 20.6 gates on it."""
        events = [
            event(well=w, subcategory=s, hours=10.0, event_id=f"{s}{i}")
            for s in ("repair", "wait", "fish")
            for i, w in enumerate(DEVELOPMENT)
        ]
        first = register.build(events, wells=DEVELOPMENT)
        second = register.build(list(reversed(events)), wells=DEVELOPMENT)
        assert [(p.subcategory, p.detail_state) for p in first.patterns] == [
            (p.subcategory, p.detail_state) for p in second.patterns
        ]

    def test_the_labelled_fraction_says_how_little_is_characterised(self) -> None:
        """A pattern with many events and two labels is one nobody has characterised."""
        events = [event(well=w, hours=10.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT)]
        built = register.build(events, wells=DEVELOPMENT, labelled_event_ids=["e0"])
        assert built.patterns[0].labelled_events == 1
        assert built.patterns[0].labelled_fraction == pytest.approx(1 / 3)

    def test_coverage_is_hours_in_recurring_patterns_over_the_corpus(self) -> None:
        events = [event(well=w, hours=10.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT)]
        events.append(event(well=DEVELOPMENT[0], subcategory="rare", hours=5.0, event_id="rare"))
        built = register.build(events, wells=DEVELOPMENT)
        assert built.corpus_hours == 35.0
        assert built.coverage == pytest.approx(30.0 / 35.0)


class TestTheCostEquivalent:
    def test_no_rate_means_no_figure_at_all(self) -> None:
        """Section 20.3 forbids a built-in day rate."""
        amount, assumption = register.cost_equivalent(1000.0, None)
        assert amount is None
        assert assumption == ""

    def test_a_supplied_rate_carries_its_assumption_with_the_number(self) -> None:
        amount, assumption = register.cost_equivalent(48.0, 500_000.0)
        assert amount == pytest.approx(1_000_000.0)
        assert "stated assumption" in assumption
        assert "not a market rate" in assumption


class TestTheCorrectionStore:
    def held_out_correction(self) -> corrections.Correction:
        return corrections.propose(
            event(well=HOLD_OUT),
            corrections.CorrectionField.EQUIPMENT,
            "mud pump 1",
            corrected_by="a person",
        )

    def development_correction(self) -> corrections.Correction:
        return corrections.propose(
            event(),
            corrections.CorrectionField.EQUIPMENT,
            "mud pump 1",
            corrected_by="a person",
        )

    def test_a_hold_out_correction_is_refused_at_write_time(self, tmp_path: Path) -> None:
        """Section 20.5 rule 1. Refused when written, not flagged when audited."""
        store = corrections.CorrectionStore(tmp_path)
        with pytest.raises(corrections.HoldOutCorrectionRefused, match="hold-out"):
            store.write("v1", [self.held_out_correction()])

    def test_nothing_is_written_when_one_correction_in_a_batch_is_refused(
        self, tmp_path: Path
    ) -> None:
        """A store that writes six and raises on the seventh has already leaked the first six."""
        store = corrections.CorrectionStore(tmp_path)
        batch = [self.development_correction(), self.held_out_correction()]
        with pytest.raises(corrections.HoldOutCorrectionRefused):
            store.write("v1", batch)
        assert store.versions() == []
        assert store.read("v1") == []

    def test_a_development_correction_is_accepted(self, tmp_path: Path) -> None:
        store = corrections.CorrectionStore(tmp_path)
        store.write("v1", [self.development_correction()])
        assert store.versions() == ["v1"]
        assert len(store.read("v1")) == 1

    def test_a_version_is_never_rewritten(self, tmp_path: Path) -> None:
        """Section 20.5 rule 2, the same reasoning as the event store."""
        store = corrections.CorrectionStore(tmp_path)
        store.write("v1", [self.development_correction()])
        with pytest.raises(corrections.StoreVersionExists, match="already has contents"):
            store.write("v1", [self.development_correction()])

    def test_an_example_is_withheld_from_the_version_that_produced_it(self, tmp_path: Path) -> None:
        """Section 20.5 rule 3: using it would show a model the answer to a coming question."""
        store = corrections.CorrectionStore(tmp_path)
        correction = self.development_correction()
        store.write("v1", [correction])
        assert store.examples_for("v1", correction.extractor_version) == []
        assert len(store.examples_for("v1", "extractor-v1")) == 1

    def test_the_content_hash_is_order_independent(self, tmp_path: Path) -> None:
        one = corrections.CorrectionStore(tmp_path / "a")
        two = corrections.CorrectionStore(tmp_path / "b")
        first = self.development_correction()
        second = corrections.propose(
            event(hours=3.0), corrections.CorrectionField.CATEGORY, "x", corrected_by="p"
        )
        one.write("v1", [first, second])
        two.write("v1", [second, first])
        assert one.content_hash("v1") == two.content_hash("v1")

    def test_the_old_value_is_taken_from_the_event_so_it_cannot_be_mistyped(self) -> None:
        source = event(hours=7.5)
        proposed = corrections.propose(
            source, corrections.CorrectionField.DURATION, "6.0", corrected_by="p"
        )
        assert proposed.old_value == "7.5"
        assert proposed.extractor_version == source.extractor_version

    @pytest.mark.parametrize(
        ("well", "expected"),
        [
            ("15/9-F-5", True),
            ("15/9-F-5 C", True),
            ("15/9-F-9", True),
            ("15/9-F-12", False),
            ("15/9-F-50", False),
            ("15/9-F-7 SOMETHING ODD", True),
        ],
    )
    def test_hold_out_detection_fails_closed_without_false_positives(
        self, well: str, expected: bool
    ) -> None:
        """A gate that raises on input it cannot parse can be made to pass by breaking its input,
        and a prefix test that ignores the separating space makes 15/9-F-50 a hold-out well."""
        assert corrections.is_hold_out(well) is expected
