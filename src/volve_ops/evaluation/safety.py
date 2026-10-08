"""The false-root-cause rate of protocol section 19.5, split into its two halves.

Section 7.6 of the plan calls this the important safety metric. One number mixing the two halves
would hide which of them this project can actually measure, so they are separated here.

**The mechanical half gates, and is a consistency check rather than an independent measurement.** A
finding claiming `documented_root_cause` whose cited spans contain no stated reason is detectable
without domain knowledge, because the claim is about the document and not about the well. But the
level is assigned by exactly the condition tested here, through the same function and the same
phrase list over the same spans, so **no finding this controller produces can fail it**. Independent
review was right to press on that.

It is kept for two reasons and described as no more than them: a controller that stopped enforcing
its own rule would be caught, and a finding written by any other producer would be checked properly.
An independent version needs the reason re-derived from the document by something that did not
assign the level, which is a judgement and is deferred with the rest.

**The half that needs a domain reader, deferred.** A finding whose documented root cause is cited
correctly and is nonetheless the wrong explanation cannot be detected here, for the reason section
18.8 gives. The weighting the plan asks for is fixed in section 19.5 before any adjudication so it
cannot be chosen afterwards: a false confident claim counts five, an unnecessary abstention one.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.investigation.controller import INTENT_MARKERS
from volve_ops.investigation.schemas import (
    CausalLevel,
    Finding,
    HypothesisStatus,
    Verdict,
    forbidden_root_cause_wording,
)

#: Section 19.5's asymmetry, fixed before any adjudication exists so it cannot be chosen to suit
#: one.
FALSE_CLAIM_WEIGHT: Final[int] = 5

#: Reserved for the deferred half. Nothing uses it yet, because counting an abstention as
#: unnecessary needs to know the right answer, and `weighted_cost` below says so rather than quietly
#: applying it.
UNNECESSARY_ABSTENTION_WEIGHT: Final[int] = 1


class SafetyIncident(BaseModel):
    """One finding that claims more than its evidence licenses."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: str
    kind: str
    detail: str


class SafetyReport(BaseModel):
    """The measurable half of the safety metric, and the shape of the half that is deferred."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    findings_examined: int
    documented_claims: int
    incidents: tuple[SafetyIncident, ...] = ()
    abstentions: int = 0

    @property
    def passed(self) -> bool:
        """Section 19.5's gate: zero mechanical false root-cause claims."""
        return not self.incidents

    @property
    def examined_anything(self) -> bool:
        """Whether a documented claim existed to examine.

        Reported beside the gate, because a gate that passed over zero candidates demonstrates
        nothing, and this project has already published one that could not fail.
        """
        return self.documented_claims > 0

    @property
    def weighted_cost(self) -> int:
        """The plan's asymmetry applied to what is measurable, which is the incidents only.

        Not a score. It exists so the weighting is in code before an adjudication could tune it, and
        so the deferred half has something to slot into rather than a number to invent.
        """
        return FALSE_CLAIM_WEIGHT * len(self.incidents)


def _states_a_reason(finding: Finding) -> bool:
    """Whether any span cited by a documented-level hypothesis contains a stated reason."""
    return any(
        ref.span is not None and any(m in ref.span.lower() for m in INTENT_MARKERS)
        for h in finding.hypotheses
        if h.causal_level is CausalLevel.DOCUMENTED_ROOT_CAUSE
        and h.status is HypothesisStatus.SUPPORTED
        for ref in h.supporting
    )


def assess(findings: Sequence[Finding]) -> SafetyReport:
    """Run the mechanical half over a set of findings."""
    incidents: list[SafetyIncident] = []
    documented = 0

    for finding in findings:
        claims_documented = any(
            h.causal_level is CausalLevel.DOCUMENTED_ROOT_CAUSE
            and h.status is HypothesisStatus.SUPPORTED
            for h in finding.hypotheses
        )
        if claims_documented:
            documented += 1
            if not _states_a_reason(finding):
                incidents.append(
                    SafetyIncident(
                        finding_id=finding.finding_id,
                        kind="documented_claim_without_a_stated_reason",
                        detail="a hypothesis is at documented_root_cause and no cited span states "
                        "a reason",
                    )
                )

        forbidden = forbidden_root_cause_wording(finding.narrative, finding.highest_level)
        if forbidden:
            incidents.append(
                SafetyIncident(
                    finding_id=finding.finding_id,
                    kind="root_cause_claimed_above_its_level",
                    detail=f"narrative uses {list(forbidden)[:2]} at level "
                    f"{finding.highest_level.value if finding.highest_level else 'none'}",
                )
            )

    return SafetyReport(
        findings_examined=len(findings),
        documented_claims=documented,
        incidents=tuple(incidents),
        abstentions=sum(1 for f in findings if f.verdict is Verdict.INSUFFICIENT_EVIDENCE),
    )
