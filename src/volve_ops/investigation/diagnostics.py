"""The mandatory diagnostic bundle of protocol section 18.2, computed deterministically.

No model touches any of this. Every channel is summarised over the episode window and over the
well's own pre-episode baseline, and the comparison between the two is what a hypothesis is later
built on.

The part that needed deciding rather than coding: what to do when a channel is absent. Imputing it
would manufacture the evidence an investigation is meant to weigh, and skipping it silently would
let a finding rest on a channel nobody can see is missing. So availability is computed per channel
and published on the finding, and section 18.2 forbids marking a hypothesis supported while a
channel it declares a dependency on is unavailable. `docs/data_profile.md` records why that is not
hypothetical: downhole pressure is usable on under a third of 15/9-F-12's producing days.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections.abc import Mapping, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.domain.day_class import ClassifiedDay, DayClass
from volve_ops.domain.sensors import UNITS, Channel, reading
from volve_ops.investigation.schemas import ChannelAvailability

#: The channels section 18.2 requires. Water cut and gas-oil ratio are derived below rather than
#: read, so they are not channels; they appear as their own summaries.
MANDATORY_CHANNELS: Final[tuple[Channel, ...]] = (
    Channel.ON_STREAM_HOURS,
    Channel.CHOKE_SIZE,
    Channel.CHOKE_DP,
    Channel.DOWNHOLE_PRESSURE,
    Channel.WELLHEAD_PRESSURE,
)

#: A channel summary needs enough days to mean anything. Below this the summary is reported with
#: its count and the channel counts as unavailable for supporting a hypothesis.
MIN_DAYS_FOR_A_SUMMARY: Final[int] = 3


class ChannelSummary(BaseModel):
    """One channel over one window: how much of it there is and what it read."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: Channel
    unit: str
    days: int
    readings: int
    median: float | None = None
    first: float | None = None
    last: float | None = None

    @property
    def usable(self) -> bool:
        return self.readings >= MIN_DAYS_FOR_A_SUMMARY


class ChannelComparison(BaseModel):
    """A channel inside the episode against the same channel before it.

    `standardised_shift` is the median shift divided by the baseline's own spread, so channels in
    bar and channels in hours can be ranked against each other. It is None whenever either window
    is too thin or the baseline does not move at all, and None is not treated as zero: a channel
    that cannot be compared is not a channel that did not change.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: Channel
    unit: str
    baseline: ChannelSummary
    episode: ChannelSummary
    shift: float | None = None
    relative_shift: float | None = None
    standardised_shift: float | None = None

    @property
    def comparable(self) -> bool:
        return self.standardised_shift is not None


class RateSummary(BaseModel):
    """Oil rate, water cut and gas-oil ratio, which are derived rather than measured."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    days: int
    median_rate_sm3_per_day: float | None = None
    median_water_cut: float | None = None
    median_gas_oil_ratio: float | None = None


class OffsetComparison(BaseModel):
    """What the other producing wells did over the same dates.

    Section 18.2 requires it because a field-wide shutdown and a well-specific problem look the same
    from one well's data, and the difference is the whole of the explanation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    wells: tuple[str, ...]
    wells_also_down: tuple[str, ...]
    median_rate_change_fraction: float | None = None

    @property
    def field_wide(self) -> bool:
        """Whether the episode looks field-wide rather than well-specific."""
        return bool(self.wells) and len(self.wells_also_down) >= max(1, len(self.wells) // 2)


class DiagnosticBundle(BaseModel):
    """Everything section 18.2 requires, with its availability record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    well: str
    onset: dt.date
    offset: dt.date
    baseline_start: dt.date
    baseline_end: dt.date

    channels: tuple[ChannelComparison, ...]
    availability: tuple[ChannelAvailability, ...]
    baseline_rates: RateSummary
    episode_rates: RateSummary
    offsets: OffsetComparison
    quarantined_days: int
    missing_days: int
    downtime_days: int

    @property
    def unavailable_mandatory(self) -> tuple[Channel, ...]:
        return tuple(a.channel for a in self.availability if a.mandatory and not a.available)

    def comparison(self, channel: Channel) -> ChannelComparison | None:
        for item in self.channels:
            if item.channel is channel:
                return item
        return None


def _summarise(days: Sequence[ClassifiedDay], channel: Channel) -> ChannelSummary:
    values = [v for v in (reading(d.day, channel) for d in days) if v is not None]
    return ChannelSummary(
        channel=channel,
        unit=UNITS[channel],
        days=len(days),
        readings=len(values),
        median=statistics.median(values) if values else None,
        first=values[0] if values else None,
        last=values[-1] if values else None,
    )


def _compare(
    baseline: Sequence[ClassifiedDay], episode: Sequence[ClassifiedDay], channel: Channel
) -> ChannelComparison:
    before, during = _summarise(baseline, channel), _summarise(episode, channel)
    shift = relative = standardised = None
    if before.usable and during.usable and before.median is not None and during.median is not None:
        shift = during.median - before.median
        if before.median != 0.0:
            relative = shift / abs(before.median)
        values = [v for v in (reading(d.day, channel) for d in baseline) if v is not None]
        spread = statistics.pstdev(values) if len(values) > 1 else 0.0
        if spread > 0.0:
            standardised = shift / spread
    return ChannelComparison(
        channel=channel,
        unit=UNITS[channel],
        baseline=before,
        episode=during,
        shift=shift,
        relative_shift=relative,
        standardised_shift=standardised,
    )


def _rates(days: Sequence[ClassifiedDay]) -> RateSummary:
    rates = [d.q_24h for d in days if d.q_24h is not None]
    cuts: list[float] = []
    gors: list[float] = []
    for classified in days:
        oil, water, gas = (
            classified.day.oil_volume_sm3,
            classified.day.water_volume_sm3,
            classified.day.gas_volume_sm3,
        )
        if oil is not None and water is not None and (oil + water) > 0.0:
            cuts.append(water / (oil + water))
        if oil is not None and gas is not None and oil > 0.0:
            gors.append(gas / oil)
    return RateSummary(
        days=len(days),
        median_rate_sm3_per_day=statistics.median(rates) if rates else None,
        median_water_cut=statistics.median(cuts) if cuts else None,
        median_gas_oil_ratio=statistics.median(gors) if gors else None,
    )


def _offsets(
    well: str,
    onset: dt.date,
    offset: dt.date,
    by_well: Mapping[str, Sequence[ClassifiedDay]],
) -> OffsetComparison:
    others = sorted(w for w in by_well if w != well)
    also_down: list[str] = []
    changes: list[float] = []
    span = (onset, offset)
    for other in others:
        days = by_well[other]
        during = [d for d in days if span[0] <= d.day.production_date <= span[1]]
        before = [d for d in days if d.day.production_date < span[0]]
        if not during or len(before) < MIN_DAYS_FOR_A_SUMMARY:
            continue
        rate_before = _rates(before[-60:]).median_rate_sm3_per_day
        rate_during = _rates(during).median_rate_sm3_per_day
        if rate_before is None or rate_during is None or rate_before <= 0.0:
            continue
        change = (rate_during - rate_before) / rate_before
        changes.append(change)
        if change <= -0.20:
            also_down.append(other)
    return OffsetComparison(
        wells=tuple(others),
        wells_also_down=tuple(also_down),
        median_rate_change_fraction=statistics.median(changes) if changes else None,
    )


def build_bundle(
    well: str,
    onset: dt.date,
    offset: dt.date,
    by_well: Mapping[str, Sequence[ClassifiedDay]],
    *,
    baseline_days: int = 60,
) -> DiagnosticBundle:
    """Run the whole bundle for one episode.

    The baseline window is the `baseline_days` of the well's own record immediately before onset,
    not a global average: the comparison that matters is the well against itself, and a field mean
    would hide a well-specific change behind five other wells.
    """
    days = list(by_well.get(well, ()))
    episode = [d for d in days if onset <= d.day.production_date <= offset]
    before = [d for d in days if d.day.production_date < onset][-baseline_days:]

    channels = tuple(_compare(before, episode, c) for c in MANDATORY_CHANNELS)
    availability = tuple(
        ChannelAvailability(
            channel=item.channel,
            unit=item.unit,
            days=item.episode.days,
            usable=item.episode.readings,
            mandatory=True,
        )
        for item in channels
    )
    return DiagnosticBundle(
        well=well,
        onset=onset,
        offset=offset,
        baseline_start=before[0].day.production_date if before else onset,
        baseline_end=before[-1].day.production_date if before else onset,
        channels=channels,
        availability=availability,
        baseline_rates=_rates(before),
        episode_rates=_rates(episode),
        offsets=_offsets(well, onset, offset, by_well),
        quarantined_days=sum(1 for d in episode if d.day_class is DayClass.QUARANTINED),
        missing_days=sum(1 for d in episode if d.day_class is DayClass.MISSING),
        downtime_days=sum(1 for d in episode if d.day_class is DayClass.DOWNTIME),
    )
