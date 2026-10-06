"""The provenance hard gate of protocol section 18.5.

Four ways a finding is blocked rather than scored, and each exists because of a specific way a
plausible-looking finding can be unfounded:

1. A cited fact id that is not in the ledger, or whose lineage does not reach measurements. A
   number with no path back to a row is an assertion wearing a citation.
2. A cited span that is not verbatim in the document it cites. One fabricated citation is one too
   many, the same reasoning as section 14.5 condition 3.
3. A number in the narrative with no fact behind it. This is the leak the other three miss: a
   finding can cite impeccably and still state a figure it invented in prose.
4. A hypothesis marked supported while a channel it declares a dependency on is unavailable. On
   this dataset that is not hypothetical: four of fourteen development episodes have no downhole
   pressure, so a pressure-driven explanation there would be asserted from an absence.

Blocked means not published. The investigation is recorded as failed, which is a reportable outcome
rather than a crash.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.investigation.schemas import (
    CURTAILED,
    EvidenceKind,
    Finding,
    HypothesisStatus,
    forbidden_root_cause_wording,
)
from volve_ops.provenance.facts import FactLedger, LineageError

#: Well and wellbore identifiers, stripped before the search for numbers. `15/9-F-12` is a name,
#: and reading it as the figures 15, 9 and 12 made the gate block every finding on its own well.
_WELL_NAME: Final[re.Pattern[str]] = re.compile(r"\b\d{1,3}/\d{1,3}-[A-Z0-9][\w\- ]*", re.I)

#: Numbers in prose. Deliberately broad: it is better to require a fact for a figure that did not
#: need one than to let an invented figure through. Years, percentages of a whole and small counts
#: written as words are excluded below.
_NUMBER: Final[re.Pattern[str]] = re.compile(r"(?<![\w.])(\d[\d\s,]*\.?\d*)(?![\w])")

#: Figures a narrative may state without a ledger fact: a date, a count of hypotheses, a day count
#: already carried by the episode, and a percentage that is itself derived from cited facts.
_EXEMPT_CONTEXT: Final[re.Pattern[str]] = re.compile(
    r"(?:\b(?:19|20)\d{2}\b|\bper\s?cent\b|%|\bday(?:s)?\b|\bhypothes[ei]s\b|\bof\s+\d+\b)", re.I
)


class GateViolation(BaseModel):
    """One reason a finding may not be published."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: str
    detail: str


class GateResult(BaseModel):
    """Whether a finding may be published, and why not when it may not."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: str
    violations: tuple[GateViolation, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.violations


def _numbers_in(text: str) -> list[str]:
    text = _WELL_NAME.sub("<well>", text)
    found: list[str] = []
    for match in _NUMBER.finditer(text):
        window = text[max(0, match.start() - 24) : match.end() + 24]
        if _EXEMPT_CONTEXT.search(window):
            continue
        found.append(match.group(1).strip())
    return found


def check(
    finding: Finding,
    ledger: FactLedger,
    documents: Mapping[str, str],
) -> GateResult:
    """Run all four rules, plus the section 18.4 wording check and the 18.3 honesty check.

    `documents` maps an event id to the comment text it came from, which is what a span is checked
    against. A span citing a document not supplied is a violation and not a skip: a gate that passes
    what it cannot see is not a gate.
    """
    violations: list[GateViolation] = []

    quantitative = [
        ("actual_volume_fact_id", finding.actual_volume_fact_id),
        ("expected_volume_fact_id", finding.expected_volume_fact_id),
        ("shortfall_fact_id", finding.shortfall_fact_id),
    ]
    if finding.shortfall_value_fact_id is not None:
        quantitative.append(("shortfall_value_fact_id", finding.shortfall_value_fact_id))

    for field, fact_id in quantitative:
        if fact_id not in ledger:
            violations.append(
                GateViolation(rule="fact_not_in_ledger", detail=f"{field} cites {fact_id}")
            )
            continue
        try:
            ledger.check(fact_id)
        except LineageError as exc:
            violations.append(
                GateViolation(rule="broken_lineage", detail=f"{field} ({fact_id}): {exc}")
            )

    for hypothesis in finding.hypotheses:
        for ref in (*hypothesis.supporting, *hypothesis.contradicting):
            if ref.kind is EvidenceKind.FACT:
                if ref.fact_id is None or ref.fact_id not in ledger:
                    violations.append(
                        GateViolation(
                            rule="fact_not_in_ledger",
                            detail=f"{hypothesis.hypothesis_id} cites {ref.fact_id}",
                        )
                    )
                continue
            if ref.span is None or ref.event_id is None:
                violations.append(
                    GateViolation(
                        rule="incomplete_citation",
                        detail=f"{hypothesis.hypothesis_id} cites a document with no span",
                    )
                )
                continue
            text = documents.get(ref.event_id)
            if text is None:
                violations.append(
                    GateViolation(
                        rule="document_not_available",
                        detail=f"{hypothesis.hypothesis_id} cites {ref.locator}, not supplied",
                    )
                )
            elif ref.span not in text:
                violations.append(
                    GateViolation(
                        rule="span_not_verbatim",
                        detail=f"{hypothesis.hypothesis_id} cites {ref.span!r} at {ref.locator}",
                    )
                )

        if hypothesis.status is HypothesisStatus.SUPPORTED:
            unavailable = {c for c in finding.unavailable_mandatory}
            missing = [c.value for c in hypothesis.required_channels if c in unavailable]
            if missing:
                violations.append(
                    GateViolation(
                        rule="supported_without_mandatory_channel",
                        detail=f"{hypothesis.hypothesis_id} is supported but {missing} is "
                        "unavailable for this well and period",
                    )
                )

    stray = _numbers_in(finding.narrative)
    if stray:
        violations.append(
            GateViolation(
                rule="unsourced_number_in_narrative",
                detail=f"no fact behind {stray[:5]}",
            )
        )

    forbidden = forbidden_root_cause_wording(finding.narrative, finding.highest_level)
    if forbidden:
        violations.append(
            GateViolation(
                rule="root_cause_wording_above_level",
                detail=f"{list(forbidden)[:3]} at level "
                f"{finding.highest_level.value if finding.highest_level else 'none'}",
            )
        )

    if finding.curtailed != (finding.stop_reason in CURTAILED):
        violations.append(
            GateViolation(
                rule="stop_reason_not_declared",
                detail=f"stop_reason {finding.stop_reason.value} with curtailed="
                f"{finding.curtailed}",
            )
        )

    return GateResult(finding_id=finding.finding_id, violations=tuple(violations))
