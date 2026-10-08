"""The post-mortem, the lessons register and the correction store, per protocol section 20.

Every gate has a failing case, which is the habit four phases of review taught: a check written in
the same breath as the thing it checks tends to test that thing against itself.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from volve_ops.extraction.npt import NPTEvent
from volve_ops.postmortem import corrections, gates, recorded_time, register

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
    equipment: str | None = None,
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
        equipment=equipment,
    )


class TestRecordedTimeOverTheRealCorpus:
    """Walked from the XML by a second path, not an independent one. Section 20.8 lists what the two
    paths share.
    """

    @pytest.fixture(scope="class")
    def walked(self) -> recorded_time.RecordedTime:
        reports = Path(__file__).resolve().parents[1] / "data" / "cache" / "ddr_xml"
        if not reports.exists():
            pytest.skip("the cached drilling reports are not present")
        return recorded_time.walk(reports)

    def test_the_categories_reconcile_to_the_independently_summed_blocks(
        self, walked: recorded_time.RecordedTime
    ) -> None:
        """Section 20.2's gate, against a block total accumulated in its own pass.

        The first version was `abs(x - x) < 0.01`, because what it compared against was a property
        defined as the sum of the two things being compared. It could not fail, and
        `docs/postmortem_results.md` called it "the one worth describing".
        """
        for well in walked.wells:
            assert well.reconciliation_error < 0.01, well.well
            assert well.summed_block_hours > 0.0, well.well

    def test_the_walk_counts_blocks_as_well_as_hours(
        self, walked: recorded_time.RecordedTime
    ) -> None:
        """Hours alone are blind to a compensating swap: one event dropped and another of equal
        duration on the same well duplicated.
        """
        assert walked.npt_blocks == 3673
        assert sum(w.timed_blocks for w in walked.wells) == walked.blocks

    def test_no_block_is_untimed(self, walked: recorded_time.RecordedTime) -> None:
        """A qualifying block that cannot be timed is a parser defect under section 14.3."""
        assert walked.untimed_blocks == 0

    def test_overlap_and_gaps_are_measured_not_assumed(
        self, walked: recorded_time.RecordedTime
    ) -> None:
        """Both are reported as their own figures. A tolerance wide enough to absorb them would be
        wide enough to hide an arithmetic error.
        """
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


def events_by_id(*events: NPTEvent) -> dict[str, NPTEvent]:
    """The mapping `CorrectionStore.write` requires.

    Required rather than defaulted since review found that no caller passed the earlier id-to-well
    version, so the only path the gating run exercised was the forgeable fallback it was meant to
    replace. The whole event rather than the well, because a fourth review measured the text scan
    catching 2.9 percent of hold-out comments while the old-value check catches all of them.
    """
    return {e.event_id: e for e in events}


class TestTheCorrectionStore:
    HELD_OUT_EVENT = event(well=HOLD_OUT)
    DEVELOPMENT_EVENT = event()

    def held_out_correction(self) -> corrections.Correction:
        return corrections.propose(
            self.HELD_OUT_EVENT,
            corrections.CorrectionField.EQUIPMENT,
            "mud pump 1",
            corrected_by="a person",
        )

    def development_correction(self) -> corrections.Correction:
        return corrections.propose(
            self.DEVELOPMENT_EVENT,
            corrections.CorrectionField.EQUIPMENT,
            "mud pump 1",
            corrected_by="a person",
        )

    def known(self) -> dict[str, NPTEvent]:
        return events_by_id(self.HELD_OUT_EVENT, self.DEVELOPMENT_EVENT)

    def test_a_hold_out_correction_is_refused_at_write_time(self, tmp_path: Path) -> None:
        """Section 20.5 rule 1. Refused when written, not flagged when audited."""
        store = corrections.CorrectionStore(tmp_path)
        with pytest.raises(corrections.HoldOutCorrectionRefused, match="hold-out"):
            store.write("v1", [self.held_out_correction()], self.known())

    def test_nothing_is_written_when_one_correction_in_a_batch_is_refused(
        self, tmp_path: Path
    ) -> None:
        """A store that writes six and raises on the seventh has already leaked the first six."""
        store = corrections.CorrectionStore(tmp_path)
        batch = [self.development_correction(), self.held_out_correction()]
        with pytest.raises(corrections.HoldOutCorrectionRefused):
            store.write("v1", batch, self.known())
        assert store.versions() == []
        assert store.read("v1") == []

    def test_a_development_correction_is_accepted(self, tmp_path: Path) -> None:
        store = corrections.CorrectionStore(tmp_path)
        store.write("v1", [self.development_correction()], self.known())
        assert store.versions() == ["v1"]
        assert len(store.read("v1")) == 1

    def test_a_version_is_never_rewritten(self, tmp_path: Path) -> None:
        """Section 20.5 rule 2, the same reasoning as the event store."""
        store = corrections.CorrectionStore(tmp_path)
        store.write("v1", [self.development_correction()], self.known())
        with pytest.raises(corrections.StoreVersionExists, match="already exists"):
            store.write("v1", [self.development_correction()], self.known())

    def test_an_example_is_withheld_from_the_version_that_produced_it(self, tmp_path: Path) -> None:
        """Section 20.5 rule 3: using it would show a model the answer to a coming question.

        `extractor-v1` is later than the `extractor-v0` the correction was made against, so it is
        served there and withheld from `extractor-v0` itself.
        """
        store = corrections.CorrectionStore(tmp_path)
        correction = self.development_correction()
        store.write("v1", [correction], self.known())
        assert store.examples_for("v1", correction.extractor_version) == []
        assert len(store.examples_for("v1", "extractor-v1")) == 1

    def test_the_content_hash_is_order_independent(self, tmp_path: Path) -> None:
        one = corrections.CorrectionStore(tmp_path / "a")
        two = corrections.CorrectionStore(tmp_path / "b")
        first = self.development_correction()
        other_event = event(hours=3.0, event_id="npt_other")
        second = corrections.propose(
            other_event, corrections.CorrectionField.CATEGORY, "x", corrected_by="p"
        )
        known = self.known() | events_by_id(other_event)
        one.write("v1", [first, second], known)
        two.write("v1", [second, first], known)
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
        and a prefix test that ignores the separating space makes 15/9-F-50 a hold-out well.
        """
        assert corrections.is_hold_out(well) is expected


NS = 'xmlns:witsml="http://www.witsml.org/schemas/1series"'


def _block(code: str, state: str, detail: str, start: str, end: str, comment: str) -> str:
    return (
        "<witsml:activity>"
        f"<witsml:dTimStart>{start}</witsml:dTimStart>"
        f"<witsml:dTimEnd>{end}</witsml:dTimEnd>"
        f"<witsml:proprietaryCode>{code}</witsml:proprietaryCode>"
        f"<witsml:state>{state}</witsml:state>"
        f"<witsml:stateDetailActivity>{detail}</witsml:stateDetailActivity>"
        f"<witsml:comments>{comment}</witsml:comments>"
        "</witsml:activity>"
    )


def synthetic_corpus(root: Path) -> Path:
    """Two reports with hand-computed totals, so CI exercises the walk without the dataset.

    Review found every test touching `recorded_time.walk` skipping on a clean checkout, which meant
    the gap and overlap arithmetic and the whole section 20.8 verification path were never executed
    on a push.

    Report one, 15/9-F-12: an 8-hour drilling block, a 2-hour interruption, then a 1-hour gap before
    a 3-hour block. Blocks sum to 13 h; wall clock covered is 13 h; gap 1 h; overlap 0. Report two,
    15/9-F-14: a 4-hour block and a 4-hour block overlapping it by 1 hour. Blocks sum to 8 h; wall
    clock 7 h; overlap 1 h; gap 0.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "15_9_F_12_2010_06_01.xml").write_text(
        f'<?xml version="1.0"?><witsml:drillReports {NS}><witsml:drillReport>'
        + _block(
            "drilling -- drill",
            "ok",
            "success",
            "2010-06-01T00:00:00+00:00",
            "2010-06-01T08:00:00+00:00",
            "Drilled ahead.",
        )
        + _block(
            "interruption -- repair",
            "ok",
            "equipment failure",
            "2010-06-01T08:00:00+00:00",
            "2010-06-01T10:00:00+00:00",
            "Mud pump 1 failed.",
        )
        + _block(
            "drilling -- drill",
            "ok",
            "success",
            "2010-06-01T11:00:00+00:00",
            "2010-06-01T14:00:00+00:00",
            "Resumed drilling.",
        )
        + "</witsml:drillReport></witsml:drillReports>",
        encoding="utf-8",
    )
    (root / "15_9_F_14_2010_06_02.xml").write_text(
        f'<?xml version="1.0"?><witsml:drillReports {NS}><witsml:drillReport>'
        + _block(
            "interruption -- wait",
            "ok",
            "success",
            "2010-06-02T00:00:00+00:00",
            "2010-06-02T04:00:00+00:00",
            "Waited on cement.",
        )
        + _block(
            "completion -- other",
            "ok",
            "success",
            "2010-06-02T03:00:00+00:00",
            "2010-06-02T07:00:00+00:00",
            "Rigged down, concurrent.",
        )
        + "</witsml:drillReport></witsml:drillReports>",
        encoding="utf-8",
    )
    return root


class TestTheWalkOnASyntheticCorpus:
    """Hand-computed totals, so this runs on a clean checkout where the dataset is absent."""

    @pytest.fixture
    def walked(self, tmp_path: Path) -> recorded_time.RecordedTime:
        return recorded_time.walk(synthetic_corpus(tmp_path / "reports"))

    def test_the_totals_are_the_ones_computed_by_hand(
        self, walked: recorded_time.RecordedTime
    ) -> None:
        assert walked.reports == 2
        assert walked.blocks == 5
        assert walked.untimed_blocks == 0
        assert walked.summed_block_hours == pytest.approx(21.0)
        assert walked.npt_hours == pytest.approx(6.0)
        assert walked.non_npt_recorded_hours == pytest.approx(15.0)

    def test_the_gap_and_the_overlap_are_measured_separately(
        self, walked: recorded_time.RecordedTime
    ) -> None:
        """The two measurements section 20.2 forbids folding into a tolerance."""
        assert walked.unclassified_gap_hours == pytest.approx(1.0)
        assert walked.concurrent_overlap_hours == pytest.approx(1.0)

    def test_every_well_reconciles(self, walked: recorded_time.RecordedTime) -> None:
        for well in walked.wells:
            assert well.reconciliation_error < 0.01, well.well

    def test_a_fabricated_well_total_does_not_reconcile(self) -> None:
        """The gate's failing case. The first version was `abs(x - x)` and could not have one."""
        fabricated = recorded_time.WellTime(
            well="15/9-F-12",
            npt_hours=100.0,
            non_npt_recorded_hours=100.0,
            summed_block_hours=13.0,
            unclassified_gap_hours=0.0,
            concurrent_overlap_hours=0.0,
            blocks=3,
            timed_blocks=3,
            npt_blocks=1,
            reports=1,
        )
        assert fabricated.reconciliation_error == pytest.approx(187.0)


class TestTheCitationSpanLimits:
    """Section 20.4's stated span limits, against what `_first_sentence` actually produces."""

    def test_a_span_is_at_least_min_span_unless_the_comment_itself_is_shorter(self) -> None:
        """The protocol says "at least 12 characters", and review was right that `MIN_SPAN` is a
        floor on the terminator index rather than on the span's length. They coincide, but only
        because of a property worth asserting rather than inferring: every path through
        `_first_sentence` returns either at least `MIN_SPAN` characters or the whole comment.
        """
        cases = [
            "POOH",
            "Held TBT",
            "CONT W.O.W.",
            "W. Continued waiting on weather for the rest of the tour.",
            "A. B. C. D. E. F. G.",
            "x" * 400,
            "Short. " + "y" * 300,
            "",
            "   ",
            "No terminator at all just a long run of words that goes past the maximum span limit "
            "and keeps going well beyond it",
        ]
        for comment in cases:
            span = register._first_sentence(comment)
            assert span in comment, comment
            if span:
                assert len(span) >= register.MIN_SPAN or span == comment.strip(), (comment, span)
            assert len(span) <= register.MAX_SPAN

    def test_every_published_span_obeys_the_limits(self) -> None:
        """Over the real corpus, where the nine spans under 12 characters are whole comments."""
        events = [
            event(well="15/9-F-12", hours=30.0, event_id="e1", comment="POOH"),
            event(well="15/9-F-14", hours=30.0, event_id="e2", comment="Held TBT"),
            event(well="15/9-F-11", hours=30.0, event_id="e3", comment="x" * 300),
        ]
        built = register.build(events, wells=DEVELOPMENT)
        for pattern in (*built.patterns, *built.excluded):
            span = pattern.representative.span
            assert span
            assert len(span) <= register.MAX_SPAN


class TestTheGatesCanEachFail:
    """Section 20.6, as functions rather than script expressions.

    Review's diagnosis after four phases: every gate that could not fail was written in the same
    file as the thing it checked, with no failing case executed. So each gate below gets one.
    """

    def walked(self, tmp_path: Path) -> recorded_time.RecordedTime:
        return recorded_time.walk(synthetic_corpus(tmp_path / "reports"))

    def built(self) -> register.Register:
        events = [event(well=w, hours=10.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT)]
        return register.build(events, wells=DEVELOPMENT)

    def test_an_empty_corpus_fails_the_precondition(self) -> None:
        empty = recorded_time.RecordedTime(wells=(), untimed_blocks=0, reports=0)
        outcome = gates.corpus_is_not_empty(
            empty,
            [],
            register.Register(
                patterns=(), excluded=(), excluded_hours=0.0, corpus_hours=0.0, wells=()
            ),
        )
        assert not outcome.passed
        assert len(outcome.detail) == 3

    def test_reconciliation_fails_when_the_store_disagrees_on_hours(self, tmp_path: Path) -> None:
        walked = self.walked(tmp_path)
        outcome = gates.categories_reconcile(walked, {"15/9-F-12": 99.0}, {"15/9-F-12": 1})
        assert not outcome.passed
        assert any("the store says" in d for d in outcome.detail)

    def test_reconciliation_fails_on_a_compensating_swap_that_hours_alone_would_miss(
        self, tmp_path: Path
    ) -> None:
        """One event dropped, another of equal duration duplicated: same hours, different count."""
        walked = self.walked(tmp_path)
        hours = {w.well: w.npt_hours for w in walked.wells}
        counts = {w.well: w.npt_blocks for w in walked.wells}
        assert gates.categories_reconcile(walked, hours, counts).passed
        counts["15/9-F-12"] += 1
        outcome = gates.categories_reconcile(walked, hours, counts)
        assert not outcome.passed
        assert any("non-productive blocks" in d for d in outcome.detail)

    def test_citations_fail_when_the_event_is_absent(self) -> None:
        outcome = gates.citations_resolve(self.built(), [])
        assert not outcome.passed
        assert outcome.examined == 1

    def test_citations_fail_on_a_paraphrased_span(self) -> None:
        built = self.built()
        events = [event(well=w, hours=10.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT)]
        broken = built.patterns[0].model_copy(
            update={
                "representative": built.patterns[0].representative.model_copy(
                    update={"span": "a paraphrase that is not in the comment"}
                )
            }
        )
        outcome = gates.citations_resolve(built.model_copy(update={"patterns": (broken,)}), events)
        assert any("not verbatim" in d for d in outcome.detail)

    def test_citations_fail_on_an_empty_span(self) -> None:
        """`"" in comment` is true for every comment, so an empty citation quoted nothing and
        satisfied the verbatim test anyway.
        """
        built = self.built()
        events = [event(well=w, hours=10.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT)]
        blank = built.patterns[0].model_copy(
            update={
                "representative": built.patterns[0].representative.model_copy(update={"span": "  "})
            }
        )
        outcome = gates.citations_resolve(built.model_copy(update={"patterns": (blank,)}), events)
        assert not outcome.passed
        assert any("empty" in d for d in outcome.detail)

    def test_citations_cover_the_excluded_patterns_the_harness_publishes(self) -> None:
        """All 38 excluded patterns are published with their own event id, document and span."""
        built = self.built()
        events = [event(well=w, hours=10.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT)]
        broken = built.patterns[0].model_copy(
            update={
                "representative": built.patterns[0].representative.model_copy(
                    update={"event_id": "an event nobody stored"}
                )
            }
        )
        moved = built.model_copy(update={"patterns": (), "excluded": (broken,)})
        outcome = gates.citations_resolve(moved, events)
        assert not outcome.passed
        assert any("excluded" in d for d in outcome.detail)

    def test_hold_out_containment_covers_the_excluded_patterns(self) -> None:
        """Review found one naming only a hold-out well, passing the first version of this gate."""
        built = self.built()
        leaked = built.patterns[0].model_copy(update={"wells": ("15/9-F-7",)})
        empty = recorded_time.RecordedTime(wells=(), untimed_blocks=0, reports=0)
        outcome = gates.hold_out_is_contained(
            built.model_copy(update={"patterns": (), "excluded": (leaked,)}), empty, []
        )
        assert not outcome.passed
        assert any("15/9-F-7" in d for d in outcome.detail)

    def test_hold_out_containment_reads_the_output_not_the_input(self) -> None:
        """Review removed the register's filter and the first version of this gate still passed."""
        built = self.built()
        leaked = built.patterns[0].model_copy(update={"wells": ("15/9-F-12", "15/9-F-5")})
        empty = recorded_time.RecordedTime(wells=(), untimed_blocks=0, reports=0)
        outcome = gates.hold_out_is_contained(
            built.model_copy(update={"patterns": (leaked,)}), empty, []
        )
        assert not outcome.passed
        assert any("15/9-F-5" in d for d in outcome.detail)

    def test_hold_out_containment_catches_a_cited_hold_out_well(self) -> None:
        built = self.built()
        pattern = built.patterns[0]
        leaked = pattern.model_copy(
            update={
                "representative": pattern.representative.model_copy(update={"well": "15/9-F-9"})
            }
        )
        empty = recorded_time.RecordedTime(wells=(), untimed_blocks=0, reports=0)
        outcome = gates.hold_out_is_contained(
            built.model_copy(update={"patterns": (leaked,)}), empty, []
        )
        assert not outcome.passed

    @pytest.mark.parametrize(
        "payload",
        [
            {"cost_equivalent_usd": 1.0, "cost_assumption": None, "day_rate_usd": 1.0},
            {"cost_equivalent_usd": None, "cost_assumption": "x", "day_rate_usd": None},
            {
                "cost_equivalent_usd": float("nan"),
                "cost_assumption": "stated assumption",
                "day_rate_usd": 1.0,
            },
            {
                "cost_equivalent_usd": float("inf"),
                "cost_assumption": "stated assumption",
                "day_rate_usd": 1.0,
            },
            {
                "cost_equivalent_usd": 1.0,
                "cost_assumption": "stated assumption",
                "day_rate_usd": 0.0,
            },
            {
                "cost_equivalent_usd": 1.0,
                "cost_assumption": "stated assumption",
                "day_rate_usd": -5.0,
            },
            {"cost_equivalent_usd": 1.0, "cost_assumption": "a vague note", "day_rate_usd": 1.0},
        ],
    )
    def test_the_currency_gate_refuses_every_unsound_combination(
        self, payload: dict[str, object]
    ) -> None:
        """Review fed the first version nan, zero and a negative rate and it approved all three."""
        assert not gates.currency_is_disclosed(payload).passed

    def test_the_currency_gate_accepts_a_sound_one_and_reports_nothing_examined_when_absent(
        self,
    ) -> None:
        sound = {
            "cost_equivalent_usd": 1_000_000.0,
            "cost_assumption": "at a stated assumption of 500,000 USD per rig day",
            "day_rate_usd": 500_000.0,
        }
        assert gates.currency_is_disclosed(sound).passed
        absent = gates.currency_is_disclosed(
            {"cost_equivalent_usd": None, "cost_assumption": None, "day_rate_usd": None}
        )
        assert absent.passed
        assert absent.vacuous

    def test_the_refusal_probe_needs_no_hold_out_data_to_pass(self, tmp_path: Path) -> None:
        """The first version probed with a real hold-out event, so it failed whenever the store
        correctly held none.
        """
        store = corrections.CorrectionStore(tmp_path / "store")
        assert gates.refusal_is_demonstrated(store).passed

    def test_the_refusal_gate_fails_on_a_store_that_accepts_a_hold_out_correction(
        self, tmp_path: Path
    ) -> None:
        """The failing case the gate had none of.

        A store that writes the probe instead of refusing it is the thing the gate exists to catch,
        so the gate has to be shown catching it. Subclassing rather than patching, because the gate
        takes a store and what it must detect is a store whose `write` does not refuse.
        """

        class PermissiveStore(corrections.CorrectionStore):
            def write(
                self,
                version: str,
                rows: Sequence[corrections.Correction],
                events: Mapping[str, NPTEvent],
            ) -> Path:
                self.root.mkdir(parents=True, exist_ok=True)
                path = self.root / f"{version}.jsonl"
                path.write_text("accepted\n", encoding="utf-8")
                return path

        outcome = gates.refusal_is_demonstrated(PermissiveStore(tmp_path / "store"))
        assert not outcome.passed
        assert any("accepted" in line for line in outcome.detail)

    def test_the_refusal_gate_fails_on_a_store_that_refuses_everything(
        self, tmp_path: Path
    ) -> None:
        """The other direction, and the one the gate's first version did not have.

        It built the accepting probe and then only asked `is_hold_out` about its well, which never
        touches the store, so a `write` that raised unconditionally satisfied all four refusing
        probes and the gate passed. Review built exactly this store and the gate approved it.
        """

        class RefusesEverything(corrections.CorrectionStore):
            def write(
                self,
                version: str,
                rows: Sequence[corrections.Correction],
                events: Mapping[str, NPTEvent],
            ) -> Path:
                raise corrections.HoldOutCorrectionRefused("no correction may ever be written")

        outcome = gates.refusal_is_demonstrated(RefusesEverything(tmp_path / "store"))
        assert not outcome.passed
        assert any("refuses everything" in line for line in outcome.detail)

    def test_the_refusal_gate_leaves_no_version_in_the_store_it_was_given(
        self, tmp_path: Path
    ) -> None:
        """The accepting probe has to write, and must not write here.

        A version left behind by a gate is a version a later run could cite, and the store is
        append-only, so it could not be removed afterwards either.
        """
        root = tmp_path / "store"
        store = corrections.CorrectionStore(root)
        assert gates.refusal_is_demonstrated(store).passed
        assert store.versions() == []
        assert not root.exists() or not list(root.glob("*.jsonl"))

    def test_reproducibility_is_actually_checked(self) -> None:
        """Pre-registered as section 20.6 item 5, dropped, and the count rewritten around it."""
        events = [event(well=w, hours=10.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT)]
        built = register.build(events, wells=DEVELOPMENT)
        outcome = gates.register_is_reproducible(built, events, wells=DEVELOPMENT)
        assert outcome.passed
        # Every field of the one pattern, not the pattern count. The first version compared four
        # fields and reported `examined=1`.
        assert outcome.examined == 15

    def test_reproducibility_fails_when_the_published_register_is_not_the_rebuilt_one(self) -> None:
        """The defect the gate had: it was handed neither the labelled nor the miscoded ids.

        So it rebuilt a register from different arguments and certified *that* as reproducible. Here
        the published register knows about a label and the rebuild is not told, which is exactly the
        shape of the original call site.
        """
        events = [event(well=w, hours=10.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT)]
        published = register.build(events, wells=DEVELOPMENT, labelled_event_ids=["e0"])
        outcome = gates.register_is_reproducible(published, events, wells=DEVELOPMENT)
        assert not outcome.passed
        assert any("field 7" in line for line in outcome.detail)

    def test_reproducibility_fails_on_a_single_altered_citation(self) -> None:
        """A span edited after the fact is a difference in one field of one pattern, and the first
        version's four-field key could not see it.
        """
        events = [event(well=w, hours=10.0, event_id=f"e{i}") for i, w in enumerate(DEVELOPMENT)]
        built = register.build(events, wells=DEVELOPMENT)
        pattern = built.patterns[0]
        tampered = built.model_copy(
            update={
                "patterns": (
                    pattern.model_copy(
                        update={
                            "representative": pattern.representative.model_copy(
                                update={"span": "something nobody wrote"}
                            )
                        }
                    ),
                )
            }
        )
        outcome = gates.register_is_reproducible(tampered, events, wells=DEVELOPMENT)
        assert not outcome.passed
        assert any("field 14" in line for line in outcome.detail)


class TestTheCorrectionStoreHolesReviewFound:
    #: The event every correction below corrects, so `old_value` can be the value the record holds.
    SUBJECT = event(well="15/9-F-12", event_id="npt_1", equipment="mud pump 1")

    def correction(self, **over: object) -> corrections.Correction:
        base: dict[str, object] = {
            "event_id": "npt_1",
            "well": "15/9-F-12",
            "field": corrections.CorrectionField.EQUIPMENT,
            "old_value": "mud pump 1",
            "new_value": "mud pump 2",
            "corrected_by": "a person",
            "corrected_at": "1970-01-01T00:00:00+00:00",
            "extractor_version": "extractor-v0",
        }
        base.update(over)
        return corrections.Correction(**base)

    def known(self, **over: NPTEvent) -> dict[str, NPTEvent]:
        """The event mapping, the development subject by default."""
        return {"npt_1": self.SUBJECT} | over

    def test_a_forged_well_cannot_smuggle_a_hold_out_event_past_the_refusal(
        self, tmp_path: Path
    ) -> None:
        """Review built this: a hold-out event id, a development well, and the hold-out event's
        verbatim comment as the old value. It wrote cleanly.
        """
        store = corrections.CorrectionStore(tmp_path)
        forged = self.correction(event_id="npt_holdout", well="15/9-19")
        held_out = event(well="15/9-F-4", event_id="npt_holdout", equipment="mud pump 1")
        with pytest.raises(corrections.HoldOutCorrectionRefused):
            store.write("v1", [forged], {"npt_holdout": held_out})
        assert store.versions() == []

    def test_the_exact_attack_review_built_is_refused_on_the_only_call_path(
        self, tmp_path: Path
    ) -> None:
        """A second review found the first fix unreachable.

        `event_wells` was optional and no caller passed it, so the gating run exercised only the
        forgeable fallback the mapping was meant to replace. No call omits it now: the parameter is
        required, and an event the store was given no well for is refused rather than trusted,
        because an unplaceable event id is what a forged one looks like.
        """
        store = corrections.CorrectionStore(tmp_path)
        forged = self.correction(
            event_id="npt_holdout_F4",
            well="15/9-F-12",
            old_value="HOLD-OUT F-4 COMMENT: stuck in hole 15/9-F-4",
            note="copied from 15/9-F-4 report 15_9_F_4_2008_01_01.xml",
        )
        with pytest.raises(corrections.HoldOutCorrectionRefused, match="cannot be placed"):
            store.write("leak1", [forged], {})
        assert store.versions() == []
        assert not list(tmp_path.glob("*.jsonl"))

    def test_an_old_value_lifted_from_another_event_is_refused(self, tmp_path: Path) -> None:
        """Rule 4, and the one that closes the attack the text scan cannot see.

        A fourth review measured the scan: the short form a comment actually uses, `F-4`, appears in
        18 of this corpus's 616 hold-out comments. So a hold-out comment pasted under an honest
        development event id and well gets past it 97 percent of the time, and the reviewer
        demonstrated that on a real pair of events. What refuses it is that the pasted text is not
        what the record says for this event, whoever wrote it and wherever it came from.
        """
        store = corrections.CorrectionStore(tmp_path)
        lifted = self.correction(
            old_value="WOW for running production riser. Brought flexible hose onto HTS."
        )
        with pytest.raises(corrections.HoldOutCorrectionRefused, match="not what the record says"):
            store.write("v1", [lifted], self.known())
        assert store.versions() == []

    def test_the_old_value_check_covers_every_correctable_field(self, tmp_path: Path) -> None:
        """One definition of "what the record says", shared with `propose`."""
        store = corrections.CorrectionStore(tmp_path)
        fields: tuple[corrections.CorrectionField, ...] = tuple(corrections.CorrectionField)
        for index, field in enumerate(fields):
            wrong = self.correction(field=field, old_value="not what the record says")
            with pytest.raises(
                corrections.HoldOutCorrectionRefused, match="not what the record says"
            ):
                store.write(f"v{index}", [wrong], self.known())
            right = self.correction(
                field=field, old_value=corrections.recorded_value(self.SUBJECT, field)
            )
            store.write(f"ok{index}", [right], self.known())
        assert len(store.versions()) == len(fields)

    @pytest.mark.parametrize(
        ("text", "refused"),
        [
            ("as recorded on 15/9-F-7: lost returns", True),
            ("copied from 15/9-F-4 report 15_9_F_4_2008_01_01.xml", True),
            ("see 15_9_F_9_2007_03_02.xml", True),
            ("15 / 9-F-4 stuck pipe", True),
            ("15/9-f-4 stuck pipe", True),
            ("15-9-F-5 washout", True),
            # A digit after the match means a different well. Over-refusal is the safe direction,
            # but refusing a correction about 15/9-F-40 because 15/9-F-4 is a prefix of it is a
            # defect: they are different wells and only one is held out.
            ("15/9-F-40 had the same issue", False),
            ("15/9-F-50 lost returns", False),
            ("mud pump 1, serial 159F40", False),
            ("15_9_F_12_2013_01_01.xml", False),
            ("mud pump 1 was renamed", False),
        ],
    )
    def test_quoted_text_is_scanned_for_hold_out_wells(
        self, tmp_path: Path, text: str, refused: bool
    ) -> None:
        """Rule 5, in the `note`, which is the only free field rule 4 does not already govern.

        An `old_value` carrying hold-out text is refused by rule 4 before the scan runs, since it is
        not what the record says. The note is the field a person writes freely, so it is where the
        scan still has work to do, and where the prefix test must stop short of the next digit.
        """
        store = corrections.CorrectionStore(tmp_path / str(abs(hash(text))))
        correction = self.correction(note=text)
        if refused:
            with pytest.raises(corrections.HoldOutCorrectionRefused, match="quotes"):
                store.write("v1", [correction], self.known())
            assert store.versions() == []
        else:
            store.write("v1", [correction], self.known())
            assert store.versions() == ["v1"]

    @pytest.mark.parametrize(
        ("well", "expected"),
        [
            ("15/9-F-04", True),
            ("15/9-F-004", True),
            ("15/9-f-04", True),
            ("15/9-F-40", False),
            ("15/9-F-50", False),
        ],
    )
    def test_a_zero_padded_hold_out_well_is_still_a_hold_out_well(
        self, well: str, expected: bool
    ) -> None:
        """`well_of` resolves `15/9-F-04` to itself, so it was in neither list and answered False.

        The resolver branch short-circuits before the fail-closed fallback, so a spelling that
        resolves to a well nobody has heard of was treated as a development well.
        """
        assert corrections.is_hold_out(well) is expected

    def test_a_development_correction_quoting_nothing_held_out_still_writes(
        self, tmp_path: Path
    ) -> None:
        """The other direction. A refusal that refuses everything is not a check."""
        store = corrections.CorrectionStore(tmp_path)
        store.write("v1", [self.correction(note="mud pump 1 was renamed")], self.known())
        assert store.versions() == ["v1"]

    def test_a_correction_whose_well_disagrees_with_its_event_is_refused(
        self, tmp_path: Path
    ) -> None:
        store = corrections.CorrectionStore(tmp_path)
        with pytest.raises(corrections.HoldOutCorrectionRefused, match="disagreement"):
            store.write(
                "v1",
                [self.correction()],
                self.known(npt_1=event(well="15/9-F-14", event_id="npt_1", equipment="mud pump 1")),
            )

    def test_an_empty_version_cannot_later_be_filled(self, tmp_path: Path) -> None:
        """A run could cite version E holding nothing, and E could later hold a correction."""
        store = corrections.CorrectionStore(tmp_path)
        store.write("v1", [], self.known())
        assert store.versions() == ["v1"]
        with pytest.raises(corrections.StoreVersionExists):
            store.write("v1", [self.correction()], self.known())

    def test_hashing_a_version_that_does_not_exist_is_refused(self, tmp_path: Path) -> None:
        """`sha256("")` is the digest of an empty version, which is a different claim."""
        store = corrections.CorrectionStore(tmp_path)
        with pytest.raises(corrections.StoreVersionMissing):
            store.content_hash("never-written")
        store.write("v1", [], self.known())
        assert store.content_hash("v1") == hashlib.sha256(b"").hexdigest()[:16]

    def test_an_over_long_version_name_is_a_bad_name_and_not_an_os_error(
        self, tmp_path: Path
    ) -> None:
        """`OSError` for a 300-character name reads the same as `OSError` for a full disk."""
        store = corrections.CorrectionStore(tmp_path)
        with pytest.raises(corrections.BadVersionName):
            store.write("v" * 300, [self.correction()], self.known())

    @pytest.mark.parametrize("name", ["../escaped", "a/b", "", ".hidden", "with space"])
    def test_a_version_name_cannot_escape_the_store_directory(
        self, tmp_path: Path, name: str
    ) -> None:
        store = corrections.CorrectionStore(tmp_path / "store")
        with pytest.raises(corrections.BadVersionName):
            store.write(name, [self.correction()], self.known())
        assert not list(tmp_path.glob("*.jsonl"))

    def test_examples_are_served_only_to_a_later_extractor_version(self, tmp_path: Path) -> None:
        """Rule 3 says later, not merely different. The first version compared for inequality, so a
        correction made against v3 was served to v0.
        """
        store = corrections.CorrectionStore(tmp_path)
        store.write("v1", [self.correction(extractor_version="extractor-v3")], self.known())
        assert store.examples_for("v1", "extractor-v0") == []
        assert store.examples_for("v1", "extractor-v3") == []
        assert len(store.examples_for("v1", "extractor-v4")) == 1

    def test_an_unparseable_extractor_version_is_withheld_rather_than_served(
        self, tmp_path: Path
    ) -> None:
        store = corrections.CorrectionStore(tmp_path)
        store.write("v1", [self.correction(extractor_version="nightly-build")], self.known())
        assert store.examples_for("v1", "extractor-v9") == []

    def test_the_audit_rows_reach_the_leakage_check(self, tmp_path: Path) -> None:
        """Written for section 19.2's fourth check and left with no call site at all."""
        store = corrections.CorrectionStore(tmp_path)
        store.write("v1", [self.correction()], self.known())
        rows = corrections.as_audit_rows(store.read("v1"))
        assert rows and rows[0]["well"] == "15/9-F-12"
