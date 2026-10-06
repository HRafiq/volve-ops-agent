"""Which sensor zeros are readings and which are absences.

The Volve production workbook records some channels as `0.00` when the measurement is missing.
A parser that mapped those to zero would hand the investigation layer a producing well sitting
at zero bar downhole, and a parser that dropped every zero would throw away real readings from
channels where zero is physically ordinary. Neither is safe, so `ProductionDay` carries the raw
value and this module is the one place that decides.

**The rule, and the evidence for it.** Two channels use zero as a sentinel:
`AVG_DOWNHOLE_PRESSURE` and `AVG_DOWNHOLE_TEMPERATURE`. Three things say so together. A gauge
three kilometres down cannot read 0 bar or 0 degrees Celsius. The two channels are zero on
exactly the same 2,312 rows, which is a paired gauge outage rather than two coincidences. And
1,924 of those rows record positive on-stream hours, so the well was flowing while the gauge
read nothing.

**The channels deliberately left alone**, because zero is a possible reading on each and
treating it as missing would be the same error in the other direction:

- `AVG_ANNULUS_PRESS`: a vented annulus sits at atmospheric, which is zero gauge.
- `AVG_WHP_P`: a bled-down shut-in well reads zero gauge at the wellhead.
- `AVG_WHT_P`: a long-shut-in wellhead approaches ambient, which can be near zero.
- `AVG_DP_TUBING` and `DP_CHOKE_SIZE`: differentials, zero when there is no flow across them.
- `AVG_CHOKE_SIZE_P`: a shut well has its choke closed, which is a reading and not a gap.

Those five are reported with their zero counts rather than silently cleaned, so a reader can
disagree with this line being drawn where it is.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.ingest.production import ProductionDay


class Channel(StrEnum):
    """A sensor or control channel on a producing well-day."""

    DOWNHOLE_PRESSURE = "downhole_pressure_bar"
    DOWNHOLE_TEMPERATURE = "downhole_temperature_c"
    TUBING_DP = "tubing_dp_bar"
    ANNULUS_PRESSURE = "annulus_pressure_bar"
    WELLHEAD_PRESSURE = "wellhead_pressure_bar"
    WELLHEAD_TEMPERATURE = "wellhead_temperature_c"
    CHOKE_DP = "choke_dp_bar"
    CHOKE_SIZE = "choke_size"
    ON_STREAM_HOURS = "on_stream_hours"


#: Channels where a recorded zero means the measurement is missing. See the module docstring.
SENTINEL_ZERO: Final[frozenset[Channel]] = frozenset(
    {Channel.DOWNHOLE_PRESSURE, Channel.DOWNHOLE_TEMPERATURE}
)

UNITS: Final[dict[Channel, str]] = {
    Channel.DOWNHOLE_PRESSURE: "bar",
    Channel.DOWNHOLE_TEMPERATURE: "degC",
    Channel.TUBING_DP: "bar",
    Channel.ANNULUS_PRESSURE: "bar",
    Channel.WELLHEAD_PRESSURE: "bar",
    Channel.WELLHEAD_TEMPERATURE: "degC",
    Channel.CHOKE_DP: "bar",
    Channel.CHOKE_SIZE: "unitless",
    Channel.ON_STREAM_HOURS: "h",
}


class ChannelCoverage(BaseModel):
    """How much of a channel is actually usable over a set of days.

    `present` counts rows carrying any value and `usable` counts rows carrying a value this
    module accepts as a reading. The two differ only on sentinel channels, and reporting both is
    the point: a presence check alone overstates downhole-pressure coverage by about fifteen
    points of the record.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: Channel
    unit: str
    days: int
    present: int
    usable: int
    zeros: int
    """How many rows record exactly zero, whether or not this channel treats that as missing.

    Separate from `sentinel_zeros` because the module docstring promises that the five non-sentinel
    channels are "reported with their zero counts rather than silently cleaned", and review found
    that promise unkept: `sentinel_zeros` is `present - usable`, which is identically zero for a
    channel with no sentinel rule, so the published table showed 0 for all five and a reader would
    have read that as "these channels have no zeros". Annulus pressure has 835 on producing days.
    """

    @property
    def fraction(self) -> float:
        return self.usable / self.days if self.days else 0.0

    @property
    def sentinel_zeros(self) -> int:
        """Zeros this channel treats as absences. Zero for every non-sentinel channel, by design."""
        return self.present - self.usable


def reading(day: ProductionDay, channel: Channel) -> float | None:
    """The channel's value on this day, or None where there is no usable measurement."""
    value = getattr(day, channel.value)
    if value is None:
        return None
    if channel in SENTINEL_ZERO and value == 0.0:
        return None
    return float(value)


def coverage(days: Sequence[ProductionDay], channel: Channel) -> ChannelCoverage:
    """Count how often a channel is present and how often it is usable."""
    present = sum(1 for d in days if getattr(d, channel.value) is not None)
    usable = sum(1 for d in days if reading(d, channel) is not None)
    zeros = sum(1 for d in days if getattr(d, channel.value) == 0.0)
    return ChannelCoverage(
        channel=channel,
        unit=UNITS[channel],
        days=len(days),
        present=present,
        usable=usable,
        zeros=zeros,
    )
