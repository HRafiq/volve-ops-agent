"""The typed boundary of an investigation, as protocol section 18 fixes it.

Three of these types exist to stop a specific way of overclaiming.

`CausalLevel` exists because "root cause identified" is the phrase a reader trusts most and the
one a choke observation most easily gets rephrased into. The level is carried on the hypothesis,
the wording permitted at each level is fixed in section 18.4, and `forbidden_root_cause_wording`
checks the narrative against it mechanically rather than trusting the prose.

`ChannelAvailability` exists because `docs/data_profile.md` records that downhole pressure is
usable on 31.2 percent of 15/9-F-12's producing days, where counting non-empty cells reports 99.8.
An investigation that reached a conclusion without a channel has to say so in the finding.

`StopReason` exists because a conclusion reached when the step budget ran out is a different object
from one reached when the evidence settled, and an aggregate that merges them describes neither.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from volve_ops.domain.sensors import Channel


class CausalLevel(StrEnum):
    """How far the evidence reaches. Section 18.4 fixes what each level permits saying."""

    PROXIMATE_DRIVER = "proximate_driver"
    SUPPORTED_MECHANISM = "supported_mechanism"
    DOCUMENTED_ROOT_CAUSE = "documented_root_cause"


class HypothesisStatus(StrEnum):
    """Where a hypothesis stands once the evidence passes are done."""

    SUPPORTED = "supported"
    PLAUSIBLE = "plausible"
    WEAK = "weak"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"


class Verdict(StrEnum):
    """The finding's overall answer. Section 18.7 requires abstention to be reachable."""

    SUPPORTED_EXPLANATION = "supported_explanation"
    MULTIPLE_PLAUSIBLE_EXPLANATIONS = "multiple_plausible_explanations"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class StopReason(StrEnum):
    """Why the investigation ended. Section 18.3 permits exactly these."""

    EVIDENCE_THRESHOLD_MET = "evidence_threshold_met"
    EVIDENCE_EXHAUSTED = "evidence_exhausted"
    MANDATORY_EVIDENCE_UNAVAILABLE = "mandatory_evidence_unavailable"
    STEP_BUDGET_REACHED = "step_budget_reached"
    COST_BUDGET_REACHED = "cost_budget_reached"


#: Stop reasons that mean the investigation was cut short rather than settled. A finding reached
#: under one of these carries that fact, per section 18.3.
CURTAILED: Final[frozenset[StopReason]] = frozenset(
    {
        StopReason.MANDATORY_EVIDENCE_UNAVAILABLE,
        StopReason.STEP_BUDGET_REACHED,
        StopReason.COST_BUDGET_REACHED,
    }
)


class EvidenceKind(StrEnum):
    """What a piece of evidence is, which decides how the provenance gate checks it."""

    FACT = "fact"
    DOCUMENT_SPAN = "document_span"


class EvidenceRef(BaseModel):
    """A pointer at something checkable, never a restatement of it.

    A fact reference carries the ledger id, so the gate can walk its lineage to measurements. A
    document-span reference carries the document, the event it belongs to and the verbatim span,
    so the gate can confirm the span is actually in the text it cites.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EvidenceKind
    fact_id: str | None = None
    document: str | None = None
    event_id: str | None = None
    span: str | None = None
    note: str | None = None

    @property
    def locator(self) -> str:
        if self.kind is EvidenceKind.FACT:
            return f"fact:{self.fact_id}"
        return f"{self.document}#{self.event_id}"


class Hypothesis(BaseModel):
    """One candidate explanation, with what supports it, what contradicts it, and what is missing.

    `required_channels` is the field the provenance gate leans on. Section 18.2 forbids marking a
    hypothesis supported while a channel it depends on is unavailable, so the dependency has to be
    declared rather than inferred from the prose.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis_id: str
    description: str
    causal_level: CausalLevel
    status: HypothesisStatus
    required_channels: tuple[Channel, ...] = ()
    supporting: tuple[EvidenceRef, ...] = ()
    contradicting: tuple[EvidenceRef, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    strength_features: dict[str, float] = Field(default_factory=dict)

    @property
    def has_evidence(self) -> bool:
        return bool(self.supporting or self.contradicting)


class ChannelAvailability(BaseModel):
    """Whether a diagnostic channel existed for this well over this episode, and how much of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: Channel
    unit: str
    days: int
    usable: int
    mandatory: bool = False

    @property
    def fraction(self) -> float:
        return self.usable / self.days if self.days else 0.0

    @property
    def available(self) -> bool:
        return self.usable > 0


class Finding(BaseModel):
    """What an investigation publishes, if the provenance gate lets it.

    Every quantitative field is a ledger id rather than a number, so the gate can check lineage
    instead of taking the narrative's word for it. `what_would_change_the_conclusion` is required
    and not decorative: a conclusion nobody can state the falsifier for is not reviewable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: str
    well: str
    episode_onset: str
    episode_offset: str

    actual_volume_fact_id: str
    expected_volume_fact_id: str
    shortfall_fact_id: str
    shortfall_value_fact_id: str | None = None
    oil_price_assumption: str | None = None

    verdict: Verdict
    hypotheses: tuple[Hypothesis, ...]
    availability: tuple[ChannelAvailability, ...]

    stop_reason: StopReason
    curtailed: bool
    steps_used: int
    narrative: str
    missing_evidence: tuple[str, ...]
    what_would_change_the_conclusion: tuple[str, ...]
    recommended_next_check: str

    investigator_version: str
    correction_store_version: str | None = None

    @property
    def leading(self) -> Hypothesis | None:
        """The hypothesis the verdict rests on, or None where the verdict is an abstention."""
        supported = [h for h in self.hypotheses if h.status is HypothesisStatus.SUPPORTED]
        if len(supported) == 1:
            return supported[0]
        return None

    @property
    def highest_level(self) -> CausalLevel | None:
        """The strongest level any supported hypothesis reached."""
        order = list(CausalLevel)
        reached = [
            h.causal_level for h in self.hypotheses if h.status is HypothesisStatus.SUPPORTED
        ]
        return max(reached, key=order.index) if reached else None

    @property
    def unavailable_mandatory(self) -> tuple[Channel, ...]:
        return tuple(a.channel for a in self.availability if a.mandatory and not a.available)


# Section 18.4 forbids root-cause wording below `documented_root_cause`. Checked against the
# narrative because that is the text a reader acts on, and a level recorded correctly in a field
# while the prose says "root cause" has still made the stronger claim.
_ROOT_CAUSE_WORDING: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\broot[\s-]?cause(?!\s+(?:unresolved|not\s+(?:established|documented)))", re.I),
    re.compile(r"\bcaused\s+by\b", re.I),
    re.compile(r"\bbecause\s+the\s+operator\b", re.I),
    re.compile(r"\bdue\s+to\s+a\s+decision\b", re.I),
)


def forbidden_root_cause_wording(narrative: str, level: CausalLevel | None) -> tuple[str, ...]:
    """Root-cause phrasing used below the level that licenses it.

    Returns the offending phrases, empty when the wording is permitted. `root cause unresolved` and
    `root cause not established` are allowed at every level: they are the disclosure section 18.4
    asks for, not the claim it forbids.
    """
    if level is CausalLevel.DOCUMENTED_ROOT_CAUSE:
        return ()
    found: list[str] = []
    for pattern in _ROOT_CAUSE_WORDING:
        found.extend(match.group(0) for match in pattern.finditer(narrative))
    return tuple(found)


def verdict_for(hypotheses: Sequence[Hypothesis]) -> Verdict:
    """The verdict the hypothesis set implies, computed rather than chosen.

    Deriving it removes one way a finding could overclaim: a model that writes
    `supported_explanation` beside two supported hypotheses, or beside none.
    """
    supported = [h for h in hypotheses if h.status is HypothesisStatus.SUPPORTED]
    plausible = [h for h in hypotheses if h.status is HypothesisStatus.PLAUSIBLE]
    if len(supported) == 1:
        return Verdict.SUPPORTED_EXPLANATION
    if len(supported) > 1:
        return Verdict.MULTIPLE_PLAUSIBLE_EXPLANATIONS
    # Nothing is supported. Two or more live candidates is the verdict's own description of
    # itself; one or none is not, and calling a single weak candidate "multiple plausible
    # explanations" would dress an abstention up as a result.
    if len(plausible) >= 2:
        return Verdict.MULTIPLE_PLAUSIBLE_EXPLANATIONS
    return Verdict.INSUFFICIENT_EVIDENCE
