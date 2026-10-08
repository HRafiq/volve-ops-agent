"""The evidence score and bands of protocol section 19.4.

Why bands and not a probability: fourteen development episodes. A calibrated probability from
fourteen outcomes has a 95 percent interval roughly 25 points wide in each bin, which is not a
calibration, and section 7.7 of the plan permits bands where the sample cannot carry more.

Why these features: every one is observable from the run, and none is a model's stated confidence.
Section 7.7 is explicit that a model's `confidence=0.83` is not a probability, and recording one
invites it to be used as one.

**Two corrections independent review forced, both of which changed published figures.**

A sixth feature, `absence_of_contradiction`, was **inert**: nothing in the codebase ever writes
`Hypothesis.contradicting`, so it read 1.0 on all fourteen findings and pulled every score upward by
a constant. The published band distribution had no `low` band at all, which was an artifact of it.
The feature is removed rather than left at 1.0, and will return when the controller can populate the
field it reads.

And the circularity is worse than first disclosed. Four of the five remaining features are derived
from inputs to the verdict itself: the standardised shift sets every hypothesis status, channel
availability triggers the unavailable-evidence stop, a documentary cause requires a supported
hypothesis, and `ran_to_completion` *is* the stop condition. So a band-versus-verdict table is
arithmetic, not a finding. The first version of the results document called the relationship "what
one would want", which was the Phase 3 mistake again: a correct table read flatteringly.

**What is deliberately not here.** No outcome rates, and so no reliability diagram, no Brier score
and no expected calibration error. Bands are calibrated against whether the conclusion was right,
and section 18.8 records that nobody available to this project can say whether it was. Section 19.4
fixes what a later version must settle before any calibrated figure is reported.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.investigation.diagnostics import DiagnosticBundle
from volve_ops.investigation.schemas import (
    CausalLevel,
    Finding,
    HypothesisStatus,
)

#: Band edges, fixed in section 19.4 before any score was computed.
HIGH_BAND: Final[float] = 0.70
MODERATE_BAND: Final[float] = 0.40

#: A channel movement this large counts as a full-strength signal. Beyond three standard deviations,
#: strong versus very strong says more about how quiet the baseline window was than about the
#: episode, which is the lesson `MIN_RELATIVE_SHIFT` recorded in amendment 4.
DEVIATION_CAP: Final[float] = 3.0

#: Decimal places the score is rounded to before it is banded. See `EvidenceScore.score`.
SCORE_PRECISION: Final[int] = 6


class EvidenceBand(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


class EvidenceScore(BaseModel):
    """The five features, the mean, and the band. Every feature is reported, not only the total.

    Reporting the components matters more than the total does: 0.5 reached with every channel and no
    document is a different situation from 0.5 reached with a document and half the channels, and a
    band alone cannot tell them apart.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    deviation_strength: float
    channel_availability: float
    documentary_cause: float
    window_completeness: float
    ran_to_completion: float

    @property
    def features(self) -> dict[str, float]:
        return {
            "deviation_strength": self.deviation_strength,
            "channel_availability": self.channel_availability,
            "documentary_cause": self.documentary_cause,
            "window_completeness": self.window_completeness,
            "ran_to_completion": self.ran_to_completion,
        }

    @property
    def circular_features(self) -> tuple[str, ...]:
        """The features derived from inputs to the verdict. Published beside any band figure.

        Four of five. `window_completeness` is the only one that is not, and it barely varies on
        this corpus, taking three values between 0.989 and 1.0.
        """
        return (
            "deviation_strength",
            "channel_availability",
            "documentary_cause",
            "ran_to_completion",
        )

    @property
    def score(self) -> float:
        """The mean of the six features, rounded to the precision the project reports.

        Rounded before banding, not after. Six features of exactly 0.40 sum to 2.4 and divide to
        0.39999999999999997, which falls into `low` while every feature sits on the `moderate` edge.
        A band that moves on floating-point error is not reproducible, and the band is what gets
        published.
        """
        return round(sum(self.features.values()) / len(self.features), SCORE_PRECISION)

    @property
    def band(self) -> EvidenceBand:
        if self.score >= HIGH_BAND:
            return EvidenceBand.HIGH
        if self.score >= MODERATE_BAND:
            return EvidenceBand.MODERATE
        return EvidenceBand.LOW


def score_finding(finding: Finding, bundle: DiagnosticBundle) -> EvidenceScore:
    """Score one finding from what its run observed."""
    shifts = [
        abs(c.standardised_shift) for c in bundle.channels if c.standardised_shift is not None
    ]
    deviation = min(max(shifts, default=0.0), DEVIATION_CAP) / DEVIATION_CAP

    mandatory = [a for a in finding.availability if a.mandatory]
    availability = sum(1 for a in mandatory if a.available) / len(mandatory) if mandatory else 0.0

    documented = any(
        h.causal_level is CausalLevel.DOCUMENTED_ROOT_CAUSE
        and h.status is HypothesisStatus.SUPPORTED
        for h in finding.hypotheses
    )

    episode_days = max(
        (a.days for a in finding.availability),
        default=0,
    )
    gaps = bundle.quarantined_days + bundle.missing_days
    completeness = max(0.0, (episode_days - gaps) / episode_days) if episode_days > 0 else 0.0

    return EvidenceScore(
        deviation_strength=deviation,
        channel_availability=availability,
        documentary_cause=1.0 if documented else 0.0,
        window_completeness=completeness,
        ran_to_completion=0.0 if finding.curtailed else 1.0,
    )
