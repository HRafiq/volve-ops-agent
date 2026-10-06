"""Stable reference windows and the episode detector, on constructed histories."""

from __future__ import annotations

import datetime as dt

import pytest

from volve_ops.domain.day_class import ClassifiedDay, DayClass
from volve_ops.domain.episodes import (
    MIN_TRIGGER_RUN,
    detect_episodes,
    reference_rate_of,
)
from volve_ops.domain.expectation import FittedExpectation, NaiveMedian28
from volve_ops.domain.regimes import (
    select_reference_window,
    stable_reference_windows,
)
from volve_ops.ingest.production import ProductionDay, WellStatus
from volve_ops.ingest.quarantine import QuarantineReason

START = dt.date(2010, 1, 1)


def day(
    offset: int,
    *,
    rate: float = 2400.0,
    choke: float | None = 50.0,
    well: str = "15/9-F-12",
    status: WellStatus = WellStatus.PRODUCING,
    day_class: DayClass = DayClass.VALID_PRODUCING,
) -> ClassifiedDay:
    return ClassifiedDay(
        day=ProductionDay(
            well=well,
            production_date=START + dt.timedelta(days=offset),
            on_stream_hours=24.0,
            oil_volume_sm3=rate,
            well_status=status,
            choke_size=choke,
            source="test",
        ),
        day_class=day_class,
        quarantine_reasons=(
            (QuarantineReason.NEGATIVE_VOLUME,) if day_class is DayClass.QUARANTINED else ()
        ),
    )


class TestStableWindows:
    def test_a_steady_run_produces_one_window(self) -> None:
        wins = stable_reference_windows([day(i) for i in range(40)])
        assert len(wins) == 1
        assert wins[0].valid_producing_days == 40

    def test_a_run_shorter_than_the_minimum_produces_none(self) -> None:
        assert stable_reference_windows([day(i) for i in range(19)]) == []

    def test_a_quarantined_day_breaks_the_window(self) -> None:
        days = [day(i) for i in range(25)] + [day(25, day_class=DayClass.QUARANTINED)]
        days += [day(i) for i in range(26, 51)]
        wins = stable_reference_windows(days)
        assert len(wins) == 2

    def test_an_activity_date_breaks_the_window(self) -> None:
        days = [day(i) for i in range(50)]
        wins = stable_reference_windows(days, activity_dates={START + dt.timedelta(days=25)})
        assert len(wins) == 2

    def test_a_status_change_breaks_the_window(self) -> None:
        days = [day(i) for i in range(25)]
        days += [
            day(i, status=WellStatus.SHUT_IN, day_class=DayClass.NON_PRODUCING)
            for i in range(25, 27)
        ]
        days += [day(i) for i in range(27, 55)]
        assert len(stable_reference_windows(days)) == 2

    def test_a_choke_change_splits_the_window(self) -> None:
        days = [day(i, choke=50.0) for i in range(25)] + [day(i, choke=80.0) for i in range(25, 50)]
        wins = stable_reference_windows(days)
        assert len(wins) >= 2

    def test_a_window_without_choke_readings_still_qualifies(self) -> None:
        wins = stable_reference_windows([day(i, choke=None) for i in range(30)])
        assert len(wins) == 1
        assert wins[0].choke_test_applied is False

    def test_mixing_wellbores_is_refused(self) -> None:
        with pytest.raises(ValueError, match="one wellbore"):
            stable_reference_windows([day(0), day(1, well="15/9-F-14")])


class TestWindowSelection:
    def test_the_most_recent_window_before_the_candidate_is_chosen(self) -> None:
        days = [day(i) for i in range(30)] + [day(i) for i in range(40, 80)]
        wins = stable_reference_windows(days, activity_dates={START + dt.timedelta(days=35)})
        chosen = select_reference_window(wins, START + dt.timedelta(days=100))
        assert chosen is not None
        assert chosen.end == max(w.end for w in wins)

    def test_none_when_no_window_precedes_the_candidate(self) -> None:
        wins = stable_reference_windows([day(i) for i in range(30)])
        assert select_reference_window(wins, START) is None


class TestEpisodeDetection:
    @staticmethod
    def _expectation() -> FittedExpectation:
        fitted = NaiveMedian28().fit([day(i) for i in range(28)])
        assert fitted is not None
        return fitted

    def test_a_steady_well_opens_no_episode(self) -> None:
        eps = detect_episodes("15/9-F-12", [day(i) for i in range(60)], self._expectation(), 2400.0)
        assert eps == []

    def test_a_short_dip_does_not_trigger(self) -> None:
        days = [day(i) for i in range(10)] + [
            day(i, rate=100.0) for i in range(10, 10 + MIN_TRIGGER_RUN - 1)
        ]
        days += [day(i) for i in range(20, 40)]
        assert detect_episodes("15/9-F-12", days, self._expectation(), 2400.0) == []

    def test_a_sustained_collapse_opens_one_episode(self) -> None:
        days = [day(i) for i in range(5)] + [day(i, rate=100.0) for i in range(5, 45)]
        eps = detect_episodes("15/9-F-12", days, self._expectation(), 2400.0)
        assert len(eps) == 1
        assert eps[0].valid_producing_days >= 10
        assert eps[0].cumulative_rate_shortfall_sm3 > eps[0].shortfall_threshold_sm3

    def test_a_one_day_recovery_does_not_split_an_episode(self) -> None:
        """Production that recovers for a day and drops again is one problem, not two."""
        days = [day(i, rate=100.0) for i in range(20)]
        days[10] = day(10, rate=2400.0)
        days += [day(i, rate=100.0) for i in range(20, 40)]
        eps = detect_episodes("15/9-F-12", days, self._expectation(), 2400.0)
        assert len(eps) == 1

    def test_reference_rate_is_the_window_median(self) -> None:
        assert (
            reference_rate_of([day(i, rate=r) for i, r in enumerate([1000.0, 2000.0, 3000.0])])
            == 2000.0
        )
        assert reference_rate_of([]) is None
