"""`strongest-deviation`, the investigation baseline fixed in protocol section 18.6.

It reads nothing. For the episode window it ranks the mandatory channels by how far each moved from
the well's own pre-episode window, in units of that window's own spread, names the largest as the
proximate driver, and reports the documented root cause as unresolved every time.

Section 18.6 explains why this is not a straw opponent, and the real episodes bear it out: of the
fourteen detected on development data, several are a plain choke-back visible in the structured data
alone. An agent that reads drilling reports has to be shown to add something beyond noticing which
number moved most, and this is the opponent that makes that demonstrable.

Like the section 3 and 14.4 baselines it cannot be amended. The thresholds below are part of its
definition.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.domain.sensors import Channel
from volve_ops.investigation.diagnostics import DiagnosticBundle
from volve_ops.investigation.schemas import CausalLevel

BASELINE_NAME: Final[str] = "strongest-deviation"

#: How far a channel must move before this baseline will name it at all, in baseline spreads.
#: Below it the baseline abstains rather than naming the largest of several small movements.
MIN_STANDARDISED_SHIFT: Final[float] = 1.0

#: How each channel's movement is read as a driver. The sign matters: a choke opening is not a
#: cause of underperformance, so only the direction consistent with lost rate is named.
_DRIVERS: Final[dict[Channel, tuple[int, str]]] = {
    Channel.ON_STREAM_HOURS: (-1, "reduced on-stream time"),
    Channel.CHOKE_SIZE: (-1, "choke reduction"),
    Channel.CHOKE_DP: (+1, "increased choke differential pressure"),
    Channel.DOWNHOLE_PRESSURE: (-1, "falling downhole pressure"),
    Channel.WELLHEAD_PRESSURE: (-1, "falling wellhead pressure"),
}


class BaselineCall(BaseModel):
    """What the baseline says about one episode."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline: str = BASELINE_NAME
    well: str
    onset: str
    proximate_driver: str | None
    channel: Channel | None
    standardised_shift: float | None
    causal_level: CausalLevel | None
    root_cause: str = "unresolved"
    skipped_channels: tuple[Channel, ...] = ()

    @property
    def abstained(self) -> bool:
        return self.proximate_driver is None


def call(bundle: DiagnosticBundle) -> BaselineCall:
    """Rank the channels and name the largest movement, or abstain.

    A channel that cannot be compared is skipped and recorded, never imputed as zero movement. The
    difference matters on this dataset: four of the fourteen development episodes have no usable
    downhole pressure, and treating that as "pressure did not move" would be a finding invented from
    an absence.
    """
    ranked: list[tuple[float, Channel, str]] = []
    skipped: list[Channel] = []
    for comparison in bundle.channels:
        if not comparison.comparable or comparison.standardised_shift is None:
            skipped.append(comparison.channel)
            continue
        direction, label = _DRIVERS[comparison.channel]
        signed = comparison.standardised_shift * direction
        if signed >= MIN_STANDARDISED_SHIFT:
            ranked.append((signed, comparison.channel, label))

    if not ranked:
        return BaselineCall(
            well=bundle.well,
            onset=bundle.onset.isoformat(),
            proximate_driver=None,
            channel=None,
            standardised_shift=None,
            causal_level=None,
            skipped_channels=tuple(skipped),
        )

    # Sort by magnitude, then by the channel's declared order, so ties are broken the same way on
    # every run rather than by whichever comparison happened to come first.
    order = list(_DRIVERS)
    best = max(ranked, key=lambda r: (round(r[0], 9), -order.index(r[1])))
    return BaselineCall(
        well=bundle.well,
        onset=bundle.onset.isoformat(),
        proximate_driver=best[2],
        channel=best[1],
        standardised_shift=best[0],
        causal_level=CausalLevel.PROXIMATE_DRIVER,
        skipped_channels=tuple(skipped),
    )
