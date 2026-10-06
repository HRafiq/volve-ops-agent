"""The tool layer: what an agent is allowed to ask for, and what it is refused.

An agent's input is untrusted, not because the model is adversarial but because a model asked
to investigate will request far more than it needs, and because text inside a source document
can try to widen a request. These tests pin the refusals.
"""

from __future__ import annotations

import datetime as dt

import pytest

from volve_ops.domain.day_class import ClassifiedDay, DayClass
from volve_ops.domain.episodes import Episode
from volve_ops.domain.production_service import ProductionHistory
from volve_ops.ingest.production import ProductionDay, WellStatus
from volve_ops.ingest.quarantine import QuarantineReason
from volve_ops.tools.production_tools import (
    get_data_quality,
    get_episode,
    get_production_history,
    list_episodes,
)
from volve_ops.tools.schemas import (
    MAX_DAYS_PER_REQUEST,
    DateRange,
    ToolError,
    ToolErrorCode,
    ToolResult,
)

START = dt.date(2010, 1, 1)


def classified(
    offset: int,
    *,
    well: str = "15/9-F-12",
    day_class: DayClass = DayClass.VALID_PRODUCING,
    hours: float | None = 24.0,
    oil: float | None = 2400.0,
) -> ClassifiedDay:
    return ClassifiedDay(
        day=ProductionDay(
            well=well,
            production_date=START + dt.timedelta(days=offset),
            on_stream_hours=hours,
            oil_volume_sm3=oil,
            well_status=WellStatus.PRODUCING,
            choke_size=50.0,
            source="test",
        ),
        day_class=day_class,
        quarantine_reasons=(
            (QuarantineReason.NEGATIVE_VOLUME,) if day_class is DayClass.QUARANTINED else ()
        ),
    )


def history(days: list[ClassifiedDay]) -> ProductionHistory:
    return ProductionHistory(days=tuple(days), duplicate_conflicts=())


def episode(well: str, onset_offset: int, shortfall: float) -> Episode:
    return Episode(
        well=well,
        onset=START + dt.timedelta(days=onset_offset),
        offset=START + dt.timedelta(days=onset_offset + 20),
        valid_producing_days=20,
        trigger_run_days=10,
        cumulative_rate_shortfall_sm3=shortfall,
        deferred_volume_sm3=100.0,
        shortfall_threshold_sm3=1000.0,
        reference_rate_sm3_per_day=2400.0,
        gap_fraction=0.0,
        open_ended=False,
    )


class TestBounds:
    def test_a_range_longer_than_the_limit_is_refused_not_truncated(self) -> None:
        """Truncating is how an agent concludes a well produced nothing in a period it never saw."""
        result = get_production_history(
            history([classified(0)]),
            "15/9-F-12",
            START,
            START + dt.timedelta(days=MAX_DAYS_PER_REQUEST + 5),
        )
        assert not result.ok
        assert result.error is not None
        assert result.error.code is ToolErrorCode.RANGE_TOO_LARGE

    def test_a_backwards_range_is_refused(self) -> None:
        result = get_production_history(
            history([classified(0)]), "15/9-F-12", START + dt.timedelta(days=10), START
        )
        assert result.error is not None
        assert result.error.code is ToolErrorCode.INVALID_RANGE

    def test_the_row_cap_backstops_a_source_that_was_never_deduplicated(self) -> None:
        """The day bound normally binds first; this is what happens when dedup did not run.

        A tool should not assume an upstream step happened. Duplicate rows per well-day would
        otherwise sail past a day-count bound and return thousands of rows.
        """
        duplicated = [classified(i % 100) for i in range(1300)]
        result = get_production_history(
            history(duplicated), "15/9-F-12", START, START + dt.timedelta(days=99)
        )
        assert result.error is not None
        assert result.error.code is ToolErrorCode.TOO_MANY_ROWS
        assert "deduplicated" in result.error.message

    def test_a_row_cap_refusal_is_a_different_code_from_a_range_refusal(self) -> None:
        """One is the caller asking for too much; the other is an upstream fault they cannot fix."""
        duplicated = [classified(i % 100) for i in range(1300)]
        rows = get_production_history(
            history(duplicated), "15/9-F-12", START, START + dt.timedelta(days=99)
        )
        span = get_production_history(
            history([classified(0)]), "15/9-F-12", START, START + dt.timedelta(days=5000)
        )
        assert rows.error is not None and span.error is not None
        assert rows.error.code is not span.error.code

    def test_exactly_the_maximum_range_is_allowed(self) -> None:
        """Pins the boundary, so tightening the bound by one day cannot pass silently."""
        end = START + dt.timedelta(days=MAX_DAYS_PER_REQUEST - 1)
        days = [classified(i) for i in range(0, MAX_DAYS_PER_REQUEST, 7)]
        assert get_production_history(history(days), "15/9-F-12", START, end).ok
        assert not get_production_history(
            history(days), "15/9-F-12", START, end + dt.timedelta(days=1)
        ).ok

    def test_the_date_range_type_enforces_its_own_bounds(self) -> None:
        with pytest.raises(ValueError, match="exceeds"):
            DateRange(start=START, end=START + dt.timedelta(days=MAX_DAYS_PER_REQUEST))


class TestRefusals:
    def test_an_unknown_well_is_an_error_with_the_known_names(self) -> None:
        result = get_production_history(
            history([classified(0)]), "15/9-NOT-A-WELL", START, START + dt.timedelta(days=5)
        )
        assert result.error is not None
        assert result.error.code is ToolErrorCode.UNKNOWN_WELL
        assert "15/9-F-12" in result.error.detail["known"]

    def test_a_range_with_no_records_says_so_rather_than_returning_empty(self) -> None:
        result = get_production_history(
            history([classified(0)]),
            "15/9-F-12",
            dt.date(2020, 1, 1),
            dt.date(2020, 2, 1),
        )
        assert result.error is not None
        assert result.error.code is ToolErrorCode.NO_DATA

    def test_a_tool_never_raises_on_bad_input(self) -> None:
        """An agent cannot act on a traceback."""
        for start, end in [
            (START + dt.timedelta(days=99), START),
            (START, START + dt.timedelta(days=5000)),
        ]:
            assert not get_production_history(history([classified(0)]), "15/9-F-12", start, end).ok

    def test_a_refusal_carries_the_message_the_validator_wrote(self) -> None:
        """Not a library's formatting of a validation error, which an agent cannot parse."""
        result = get_production_history(
            history([classified(0)]), "15/9-F-12", START + dt.timedelta(days=10), START
        )
        assert result.error is not None
        assert result.error.message.startswith("end ")
        assert "pydantic" not in result.error.message
        assert "validation error" not in result.error.message.lower()

    def test_an_error_detail_key_cannot_collide_with_the_result_fields(self) -> None:
        """A layer whose contract is never to raise must not raise while building its error."""
        error = ToolError(
            code=ToolErrorCode.NO_DATA, message="m", detail={"code": "x", "message": "y"}
        )
        assert ToolResult[None](error=error).error is error


class TestResults:
    def test_counts_travel_with_the_rows(self) -> None:
        days = [classified(i) for i in range(5)]
        days.append(classified(5, day_class=DayClass.DOWNTIME, hours=0.0, oil=0.0))
        days.append(classified(6, day_class=DayClass.QUARANTINED))
        result = get_production_history(
            history(days), "15/9-F-12", START, START + dt.timedelta(days=6)
        )
        assert result.ok and result.value is not None
        assert result.value.valid_producing_days == 5
        assert result.value.downtime_days == 1
        assert result.value.quarantined_days == 1
        assert len(result.value.days) == 7

    def test_a_rate_is_reported_only_where_the_domain_defines_one(self) -> None:
        days = [classified(0), classified(1, day_class=DayClass.PARTIAL, hours=3.0, oil=200.0)]
        result = get_production_history(
            history(days), "15/9-F-12", START, START + dt.timedelta(days=1)
        )
        assert result.value is not None
        assert result.value.days[0].normalised_rate_sm3_per_day is not None
        assert result.value.days[1].normalised_rate_sm3_per_day is None

    def test_data_quality_reports_the_gap_fraction_and_the_reasons(self) -> None:
        days = [classified(i) for i in range(8)]
        days.append(classified(8, day_class=DayClass.QUARANTINED))
        days.append(classified(9, day_class=DayClass.MISSING, hours=None))
        result = get_data_quality(history(days), "15/9-F-12", START, START + dt.timedelta(days=9))
        assert result.value is not None
        assert result.value.gap_fraction == pytest.approx(0.2)
        assert result.value.quarantine_reasons["negative_volume"] == 1
        assert result.value.valid_producing_days == 8


class TestEpisodeTools:
    def test_episodes_come_back_most_costly_first(self) -> None:
        eps = [episode("A", 0, 100.0), episode("B", 10, 900.0), episode("A", 40, 500.0)]
        result = list_episodes(eps)
        assert result.value is not None
        assert [e.cumulative_rate_shortfall_sm3 for e in result.value] == [900.0, 500.0, 100.0]

    def test_filtering_by_well_works_and_an_empty_filter_is_an_error(self) -> None:
        eps = [episode("A", 0, 100.0), episode("B", 10, 900.0)]
        assert len(list_episodes(eps, "A").value or ()) == 1
        missing = list_episodes(eps, "C")
        assert missing.error is not None
        assert missing.error.code is ToolErrorCode.NO_DATA

    def test_one_episode_is_addressed_by_well_and_onset(self) -> None:
        eps = [episode("A", 0, 100.0)]
        assert get_episode(eps, "A", START).ok
        absent = get_episode(eps, "A", dt.date(1999, 1, 1))
        assert absent.error is not None
        assert absent.error.code is ToolErrorCode.NOT_FOUND


class TestEveryDayClassIsCounted:
    def test_non_producing_days_are_reported(self) -> None:
        """They are 6,181 of 15,634 rows in the real dataset and had no count at all."""
        days = [classified(i) for i in range(3)]
        days += [classified(i, day_class=DayClass.NON_PRODUCING, oil=None) for i in range(3, 10)]
        result = get_production_history(
            history(days), "15/9-F-12", START, START + dt.timedelta(days=9)
        )
        assert result.value is not None
        view = result.value
        assert view.non_producing_days == 7
        counted = (
            view.valid_producing_days
            + view.downtime_days
            + view.partial_days
            + view.non_producing_days
            + view.quarantined_days
            + view.missing_days
        )
        assert counted == view.rows

    def test_calendar_days_with_no_row_at_all_are_reported(self) -> None:
        """Absent days are invisible to a count of rows classified missing."""
        days = [classified(0), classified(9)]
        result = get_production_history(
            history(days), "15/9-F-12", START, START + dt.timedelta(days=9)
        )
        assert result.value is not None
        assert result.value.absent_days == 8
        assert result.value.missing_days == 0


class TestUsableFraction:
    def test_a_window_of_injector_days_reports_almost_no_gaps_and_no_usable_evidence(
        self,
    ) -> None:
        """The case that made gap_fraction alone misleading: 1.1% gaps, zero usable days."""
        days = [classified(i, day_class=DayClass.NON_PRODUCING, oil=None) for i in range(100)]
        result = get_data_quality(history(days), "15/9-F-12", START, START + dt.timedelta(days=99))
        assert result.value is not None
        assert result.value.gap_fraction == 0.0
        assert result.value.usable_fraction == 0.0
        assert result.value.valid_producing_days == 0

    def test_usable_fraction_is_measured_against_the_range_not_the_rows(self) -> None:
        days = [classified(i) for i in range(50)]
        result = get_data_quality(history(days), "15/9-F-12", START, START + dt.timedelta(days=99))
        assert result.value is not None
        assert result.value.range_days == 100
        assert result.value.rows_present == 50
        assert result.value.absent_days == 50
        assert result.value.usable_fraction == pytest.approx(0.5)
