"""Deterministic NPT extraction and the two fixed baselines."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from volve_ops.extraction.baselines import (
    STATE_DETAIL_TO_CAUSE,
    SUBCATEGORY_TO_CAUSE,
    echo_state_detail,
    echo_subcategory,
)
from volve_ops.extraction.npt import (
    CauseLabel,
    NPTEvent,
    extract_from_report,
    is_non_productive,
)
from volve_ops.ingest.quarantine import UnsafeInputError

NS = 'xmlns:witsml="http://www.witsml.org/schemas/1series"'


def report(tmp_path: Path, activities: str, name: str = "15_9_F_12_2010_06_01.xml") -> Path:
    path = tmp_path / name
    path.write_text(
        f'<?xml version="1.0"?><witsml:drillReports {NS}><witsml:drillReport>'
        f"{activities}</witsml:drillReport></witsml:drillReports>",
        encoding="utf-8",
    )
    return path


def activity(
    code: str = "interruption -- repair",
    state: str = "fail",
    detail: str = "equipment failure",
    comment: str = "Mud pump 1 failed, changed liners.",
    start: str = "2010-06-01T04:00:00+02:00",
    end: str = "2010-06-01T06:30:00+02:00",
) -> str:
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


class TestWhatCountsAsNonProductive:
    """Protocol section 14.1: an interruption head OR a fail state, not the head alone."""

    @pytest.mark.parametrize(
        ("code", "state", "expected"),
        [
            ("interruption -- repair", "ok", True),
            ("interruption -- other", "ok", True),
            ("drilling -- casing", "fail", True),
            ("drilling -- drill", "fail", True),
            ("drilling -- casing", "ok", False),
            ("plug abandon -- trip", "ok", False),
            ("INTERRUPTION -- repair", "OK", True),
        ],
    )
    def test_the_rule(self, code: str, state: str, expected: bool) -> None:
        assert is_non_productive(code, state) is expected

    def test_a_failed_casing_run_is_lost_time_whatever_it_was_filed_under(
        self, tmp_path: Path
    ) -> None:
        """96 such blocks exist. An earlier draft would have called counting them a defect."""
        events = list(
            extract_from_report(report(tmp_path, activity(code="drilling -- casing", state="fail")))
        )
        assert len(events) == 1
        assert events[0].category == "drilling"

    def test_an_ordinary_drilling_block_is_not_an_event(self, tmp_path: Path) -> None:
        events = list(
            extract_from_report(report(tmp_path, activity(code="drilling -- drill", state="ok")))
        )
        assert events == []


class TestExtraction:
    def test_duration_comes_from_the_timestamps(self, tmp_path: Path) -> None:
        (event,) = extract_from_report(report(tmp_path, activity()))
        assert event.duration_hours == pytest.approx(2.5)
        assert event.start_time.hour == 4

    def test_the_source_fields_are_carried_not_interpreted(self, tmp_path: Path) -> None:
        (event,) = extract_from_report(report(tmp_path, activity()))
        assert event.category == "interruption"
        assert event.subcategory == "repair"
        assert event.state_detail == "equipment failure"
        assert event.comment.startswith("Mud pump 1")

    def test_the_cause_is_left_empty_for_attribution(self, tmp_path: Path) -> None:
        """A deterministic extractor that guessed a cause would be the thing to prevent."""
        (event,) = extract_from_report(report(tmp_path, activity()))
        assert event.cause is None
        assert event.evidence_span is None
        assert event.has_attribution is False

    def test_the_well_is_canonical_and_the_wellbore_is_kept(self, tmp_path: Path) -> None:
        path = report(tmp_path, activity(), name="15_9_F_15_D_2013_11_11.xml")
        (event,) = extract_from_report(path)
        assert event.wellbore == "15/9-F-15 D"
        assert event.well == "15/9-F-15"
        assert event.report_date == dt.date(2013, 11, 11)

    def test_event_ids_are_stable_across_runs(self, tmp_path: Path) -> None:
        """A re-run must not renumber events, or every correction loses its referent."""
        path = report(
            tmp_path,
            activity()
            + activity(start="2010-06-01T08:00:00+02:00", end="2010-06-01T09:00:00+02:00"),
        )
        first = [e.event_id for e in extract_from_report(path)]
        second = [e.event_id for e in extract_from_report(path)]
        assert first == second
        assert len(set(first)) == 2

    def test_a_qualifying_block_without_timestamps_is_refused_not_skipped(
        self, tmp_path: Path
    ) -> None:
        """Section 14.3 requires every 14.1 block to become exactly one event.

        Skipping one silently, as an earlier version did, would let the exactness pass mark
        pass by losing the evidence against it.
        """
        broken = (
            "<witsml:activity>"
            "<witsml:proprietaryCode>interruption -- repair</witsml:proprietaryCode>"
            "<witsml:state>ok</witsml:state></witsml:activity>"
        )
        with pytest.raises(UnsafeInputError, match="no usable timestamps"):
            list(extract_from_report(report(tmp_path, broken)))

    def test_a_productive_block_without_timestamps_is_simply_not_an_event(
        self, tmp_path: Path
    ) -> None:
        """The rule applies to blocks that qualify under 14.1, not to every block."""
        ignorable = (
            "<witsml:activity>"
            "<witsml:proprietaryCode>drilling -- drill</witsml:proprietaryCode>"
            "<witsml:state>ok</witsml:state></witsml:activity>"
        )
        assert list(extract_from_report(report(tmp_path, ignorable))) == []

    def test_an_empty_comment_is_flagged_for_review(self, tmp_path: Path) -> None:
        (event,) = extract_from_report(report(tmp_path, activity(comment="")))
        assert event.needs_review
        assert "no_comment" in event.review_reasons

    def test_a_filename_without_a_date_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(UnsafeInputError, match="no date"):
            list(extract_from_report(report(tmp_path, activity(), name="no_date_here.xml")))

    def test_a_hostile_report_is_refused_by_the_hardened_parser(self, tmp_path: Path) -> None:
        path = tmp_path / "15_9_F_12_2010_06_01.xml"
        path.write_text(
            "<?xml version='1.0'?><!DOCTYPE r [<!ENTITY x SYSTEM 'file:///etc/passwd'>]><r>&x;</r>",
            encoding="utf-8",
        )
        with pytest.raises(UnsafeInputError):
            list(extract_from_report(path))


class TestBaselines:
    def test_the_mappings_are_the_ones_the_protocol_fixed(self) -> None:
        """Both tables are exempt from amendment, so a change here is a protocol change."""
        assert SUBCATEGORY_TO_CAUSE["repair"] is CauseLabel.EQUIPMENT_FAILURE
        assert SUBCATEGORY_TO_CAUSE["maintain"] is CauseLabel.EQUIPMENT_MAINTENANCE
        assert SUBCATEGORY_TO_CAUSE["other"] is CauseLabel.NOT_STATED
        assert SUBCATEGORY_TO_CAUSE["wait"] is CauseLabel.NOT_STATED
        assert len(SUBCATEGORY_TO_CAUSE) == 10

        assert STATE_DETAIL_TO_CAUSE["equipment failure"] is CauseLabel.EQUIPMENT_FAILURE
        assert STATE_DETAIL_TO_CAUSE["success"] is CauseLabel.NOT_STATED
        assert STATE_DETAIL_TO_CAUSE["operation failed"] is CauseLabel.NOT_STATED
        assert len(STATE_DETAIL_TO_CAUSE) == 6

    def test_both_baselines_can_decline(self) -> None:
        """A baseline that cannot say not_stated scores zero on the largest class."""
        assert CauseLabel.NOT_STATED in SUBCATEGORY_TO_CAUSE.values()
        assert CauseLabel.NOT_STATED in STATE_DETAIL_TO_CAUSE.values()

    def test_an_unmapped_value_falls_to_not_stated(self) -> None:
        event = NPTEvent(
            event_id="npt_x",
            well="15/9-F-12",
            wellbore="15/9-F-12",
            source_document="d.xml",
            report_date=dt.date(2010, 6, 1),
            start_time=dt.datetime(2010, 6, 1, 4),
            end_time=dt.datetime(2010, 6, 1, 5),
            duration_hours=1.0,
            activity_code="interruption -- novel",
            category="interruption",
            subcategory="novel",
            state="ok",
            state_detail="something new",
            comment="x",
        )
        assert echo_subcategory(event) is CauseLabel.NOT_STATED
        assert echo_state_detail(event) is CauseLabel.NOT_STATED

    def test_the_two_baselines_are_genuinely_different(self, tmp_path: Path) -> None:
        """They disagree on about two thirds of the corpus, which is why both are named."""
        (event,) = extract_from_report(
            report(tmp_path, activity(code="interruption -- other", detail="equipment failure"))
        )
        assert echo_subcategory(event) is CauseLabel.NOT_STATED
        assert echo_state_detail(event) is CauseLabel.EQUIPMENT_FAILURE
