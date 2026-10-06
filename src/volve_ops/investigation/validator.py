"""The provenance hard gate of protocol section 18.5.

Independent review broke the first version of this module, and the holes are worth recording because
each was a way a finding could be unfounded and pass:

- The well-name pattern globbed `[\\w\\- ]*`, so stripping `15/9-F-12` from a narrative ate the rest
  of the sentence with it. Every published finding opens "Well X produced below expectation over the
  episode window", so the unsourced-number rule had never examined a single first sentence.
- Numbers were exempted by proximity: any figure within 24 characters of `day`, a year or `%` was
  waved through, which is most prose. `Production fell by 4200 Sm3 over 31 days` passed.
- A citation's document name was never checked against anything, so a fabricated filename published
  beside a real span.
- A citation's event was never checked against the finding's own well or window, so a finding about
  one well in 2011 could cite a different well's report from 2007. The comments are boilerplate
  repeated across wells, so this is the exact failure the layer exists to prevent.

All four are closed below. The gate now needs the cited events' metadata rather than their text
alone, which is why it takes `CitableDocument` instead of a string map.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.investigation.schemas import (
    CURTAILED,
    CausalLevel,
    EvidenceKind,
    Finding,
    HypothesisStatus,
    forbidden_root_cause_wording,
)
from volve_ops.provenance.facts import FactLedger, LineageError

#: How far outside the episode a cited report may be dated. Matches the controller's retrieval
#: window: a report just before onset is often what explains the episode, and one two years away is
#: not evidence about it whatever its text says.
CITATION_WINDOW_DAYS: Final[int] = 45

#: Well and wellbore identifiers. Anchored rather than globbed: the suffix is an optional wellbore
#: letter, so the pattern stops at the name instead of consuming the sentence after it.
_WELL_NAME: Final[re.Pattern[str]] = re.compile(
    r"\b\d{1,3}/\d{1,3}-(?:[A-Z]-)?\d{1,3}(?:\s+[A-Z]{1,2}\d?\b)?"
)

#: ISO dates, stripped before the search for numbers. A date is a locator, like a well name, and not
#: a quantity: `2010-03-02` would otherwise read as the figures 03 and 02.
_ISO_DATE: Final[re.Pattern[str]] = re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b")

#: Numbers in prose. Every figure needs a fact behind it, with two exemptions decided on the token
#: itself rather than on its neighbourhood: a four-digit year, and a number written as a percentage.
#: The previous proximity test exempted most sentences by accident.
_NUMBER: Final[re.Pattern[str]] = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?![\w])")
_YEAR: Final[re.Pattern[str]] = re.compile(r"^(?:19|20)\d{2}$")


class CitableDocument(BaseModel):
    """What the gate needs about a cited event to check the citation rather than trust it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    source_document: str
    well: str
    report_date: dt.date
    text: str


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


def unsourced_numbers(text: str) -> list[str]:
    """Figures in prose that need a fact behind them.

    Exported because the controller's narrative generator is checked against it in tests: the
    narratives this project produces state no figures at all, by design, so this rule is not
    exercised by them. It exists for any other generator, a model-backed one above all.
    """
    stripped = _ISO_DATE.sub("<date>", _WELL_NAME.sub("<well>", text))
    found: list[str] = []
    for match in _NUMBER.finditer(stripped):
        token = match.group(1)
        if _YEAR.match(token):
            continue
        tail = stripped[match.end() : match.end() + 9]
        if tail.startswith("%") or tail.lstrip().startswith(("percent", "per cent")):
            continue
        found.append(token)
    return found


def _check_citation(
    finding: Finding,
    hypothesis_id: str,
    document: str | None,
    event_id: str | None,
    span: str | None,
    documents: Mapping[str, CitableDocument],
) -> list[GateViolation]:
    """One document citation, against the text, the filename, the well and the window."""
    if span is None or event_id is None:
        return [
            GateViolation(
                rule="incomplete_citation",
                detail=f"{hypothesis_id} cites a document with no span or no event",
            )
        ]
    cited = documents.get(event_id)
    if cited is None:
        return [
            GateViolation(
                rule="document_not_available",
                detail=f"{hypothesis_id} cites {event_id}, which was not supplied",
            )
        ]

    out: list[GateViolation] = []
    if span not in cited.text:
        out.append(
            GateViolation(
                rule="span_not_verbatim",
                detail=f"{hypothesis_id} cites {span!r} at {event_id}, which does not contain it",
            )
        )
    if document is not None and document != cited.source_document:
        out.append(
            GateViolation(
                rule="document_name_wrong",
                detail=f"{hypothesis_id} names {document!r} but {event_id} came from "
                f"{cited.source_document!r}",
            )
        )
    # A citation has to be about this well. Comments repeat verbatim across wells, so a span can be
    # genuinely present in a document that has nothing to do with the finding.
    if cited.well not in {finding.well, _well_of(finding.well)}:
        out.append(
            GateViolation(
                rule="citation_from_another_well",
                detail=f"{hypothesis_id} cites {event_id} on {cited.well}, and this finding is "
                f"about {finding.well}",
            )
        )
    onset = dt.date.fromisoformat(finding.episode_onset)
    offset = dt.date.fromisoformat(finding.episode_offset)
    window = dt.timedelta(days=CITATION_WINDOW_DAYS)
    if not (onset - window) <= cited.report_date <= (offset + window):
        out.append(
            GateViolation(
                rule="citation_outside_the_window",
                detail=f"{hypothesis_id} cites {event_id} dated {cited.report_date}, outside "
                f"{onset}..{offset} plus or minus {CITATION_WINDOW_DAYS} days",
            )
        )
    return out


def _well_of(wellbore: str) -> str:
    """The well a wellbore belongs to, for comparing a citation's well against a finding's.

    Deliberately local and crude rather than importing the domain resolver: this is a comparison in
    a gate, and a gate that can raise on its input is a gate that can be made to pass by breaking
    its input.
    """
    head, _, tail = wellbore.rpartition(" ")
    return head if head and len(tail) <= 3 else wellbore


def check(
    finding: Finding,
    ledger: FactLedger,
    documents: Mapping[str, CitableDocument],
) -> GateResult:
    """Run every section 18.5 rule, plus the 18.4 wording check and the 18.3 honesty check."""
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

    unavailable = set(finding.unavailable_mandatory)
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
            violations.extend(
                _check_citation(
                    finding,
                    hypothesis.hypothesis_id,
                    ref.document,
                    ref.event_id,
                    ref.span,
                    documents,
                )
            )

        if hypothesis.status is HypothesisStatus.SUPPORTED:
            missing = [c.value for c in hypothesis.required_channels if c in unavailable]
            if missing:
                violations.append(
                    GateViolation(
                        rule="supported_without_mandatory_channel",
                        detail=f"{hypothesis.hypothesis_id} is supported but {missing} is "
                        "unavailable for this well and period",
                    )
                )

    # Every published prose field, not the narrative alone. An invented figure in the recommended
    # next check is published just as widely as one in the narrative.
    prose = {
        "narrative": finding.narrative,
        "recommended_next_check": finding.recommended_next_check,
        **{
            f"what_would_change_the_conclusion[{i}]": line
            for i, line in enumerate(finding.what_would_change_the_conclusion)
        },
        **{f"missing_evidence[{i}]": line for i, line in enumerate(finding.missing_evidence)},
    }
    for field, text in prose.items():
        stray = unsourced_numbers(text)
        if stray:
            violations.append(
                GateViolation(
                    rule="unsourced_number_in_prose",
                    detail=f"{field}: no fact behind {stray[:5]}",
                )
            )

    # A finding that reached the documented level may not also disclaim it. The wording check only
    # looks downward, so this is the mirror of it: review found a finding at `documented_root_cause`
    # whose narrative still said "Root cause unresolved", which is the same defect pointing the
    # other way and is worse, because it understates evidence the project did have.
    if (
        finding.highest_level is CausalLevel.DOCUMENTED_ROOT_CAUSE
        and "root cause unresolved" in finding.narrative.lower()
    ):
        violations.append(
            GateViolation(
                rule="documented_level_disclaims_itself",
                detail="the finding reached documented_root_cause and the narrative calls it "
                "unresolved",
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
