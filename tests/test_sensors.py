"""Which sensor zeros are readings and which are absences.

The whole module is one judgement, so the tests pin both halves of it: the two channels where a
zero is a missing measurement, and the five where a zero is a real one and dropping it would be
the same mistake in the other direction.
"""

from __future__ import annotations

import datetime as dt

import pytest

from volve_ops.domain.sensors import (
    SENTINEL_ZERO,
    UNITS,
    Channel,
    ChannelCoverage,
    coverage,
    reading,
)
from volve_ops.ingest.production import ProductionDay, WellStatus


def day(**over: object) -> ProductionDay:
    base: dict[str, object] = {
        "well": "15/9-F-12",
        "production_date": dt.date(2010, 6, 1),
        "on_stream_hours": 24.0,
        "oil_volume_sm3": 900.0,
        "well_status": WellStatus.PRODUCING,
        "choke_size": 50.0,
        "downhole_pressure_bar": 230.0,
        "downhole_temperature_c": 103.0,
        "tubing_dp_bar": 175.0,
        "annulus_pressure_bar": 16.0,
        "wellhead_pressure_bar": 38.0,
        "wellhead_temperature_c": 80.0,
        "choke_dp_bar": 2.4,
        "source": "wb.xlsx",
    }
    base.update(over)
    return ProductionDay(**base)  # type: ignore[arg-type]


class TestTheSentinelRule:
    def test_exactly_the_two_downhole_channels_are_sentinels(self) -> None:
        """Named explicitly, because every other channel can legitimately read zero."""
        assert {Channel.DOWNHOLE_PRESSURE, Channel.DOWNHOLE_TEMPERATURE} == SENTINEL_ZERO

    @pytest.mark.parametrize("channel", [Channel.DOWNHOLE_PRESSURE, Channel.DOWNHOLE_TEMPERATURE])
    def test_a_zero_on_a_sentinel_channel_is_no_measurement(self, channel: Channel) -> None:
        assert reading(day(**{channel.value: 0.0}), channel) is None

    @pytest.mark.parametrize(
        "channel",
        [
            Channel.ANNULUS_PRESSURE,
            Channel.WELLHEAD_PRESSURE,
            Channel.WELLHEAD_TEMPERATURE,
            Channel.TUBING_DP,
            Channel.CHOKE_DP,
            Channel.CHOKE_SIZE,
        ],
    )
    def test_a_zero_elsewhere_is_a_reading(self, channel: Channel) -> None:
        """A vented annulus, a bled-down wellhead and a shut choke all read zero for real."""
        assert reading(day(**{channel.value: 0.0}), channel) == 0.0

    def test_a_missing_value_is_none_on_every_channel(self) -> None:
        for channel in Channel:
            assert reading(day(**{channel.value: None}), channel) is None

    def test_a_negative_pressure_is_passed_through_rather_than_silently_dropped(self) -> None:
        """Not this module's judgement to make. The day classifier owns physical plausibility."""
        assert reading(day(downhole_pressure_bar=-5.0), Channel.DOWNHOLE_PRESSURE) == -5.0

    def test_every_channel_declares_a_unit(self) -> None:
        assert set(UNITS) == set(Channel)


class TestCoverage:
    def test_present_and_usable_differ_only_on_a_sentinel_channel(self) -> None:
        days = [day(), day(downhole_pressure_bar=0.0), day(downhole_pressure_bar=None)]
        pressure = coverage(days, Channel.DOWNHOLE_PRESSURE)
        assert pressure.days == 3
        assert pressure.present == 2
        assert pressure.usable == 1
        assert pressure.sentinel_zeros == 1
        assert pressure.fraction == pytest.approx(1 / 3)

        wellhead = coverage(days, Channel.WELLHEAD_PRESSURE)
        assert wellhead.present == wellhead.usable == 3
        assert wellhead.sentinel_zeros == 0

    def test_a_presence_check_overstates_a_sentinel_channel(self) -> None:
        """The reason this module exists: 2,312 rows of the real record read zero downhole."""
        days = [day(downhole_pressure_bar=0.0) for _ in range(9)] + [day()]
        pressure = coverage(days, Channel.DOWNHOLE_PRESSURE)
        assert pressure.present == 10
        assert pressure.usable == 1

    def test_no_days_is_zero_coverage_rather_than_a_division_error(self) -> None:
        assert coverage([], Channel.DOWNHOLE_PRESSURE).fraction == 0.0

    def test_the_coverage_record_is_frozen(self) -> None:
        pressure = coverage([day()], Channel.DOWNHOLE_PRESSURE)
        with pytest.raises(ValueError, match="frozen"):
            pressure.usable = 99  # type: ignore[misc]
        assert isinstance(pressure, ChannelCoverage)
