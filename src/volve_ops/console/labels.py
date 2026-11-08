"""Operator-facing labels. The console design's decision 5, and protocol section 21.4.

Schema enum values do not change: the backend keeps `proximate_driver` and
`insufficient_evidence`, because renaming a stored value to suit a screen is how a manifest stops
matching the runs that produced it. The UI shows a label instead, and the mapping lives here so
there is one place it can be checked rather than one per component.

Two rules this file exists to enforce.

**Abstention is not described in evaluation vocabulary.** "Insufficient evidence, no conclusion
issued" is what an operator reads. The words "abstained", "abstention" and "success mode" belong in
System Health, where the reader is the engineer who chose them, and `is_operator_safe` is how a test
can say so about a whole payload.

**"Approve" is not used for a review action.** The design's decision 6: approving a finding could be
read as approving an operational action, and this system has no actuation path at all. The label is
"Confirm finding", and the review panel says in words that a review records a judgement of the
assessment and authorises nothing.
"""

from __future__ import annotations

from typing import Final

#: Section 18.4's causal levels, and the absence of one.
CAUSAL_LEVEL: Final[dict[str | None, str]] = {
    "proximate_driver": "Operational driver",
    "supported_mechanism": "Supported mechanism",
    "documented_root_cause": "Documented root cause",
    None: "Unresolved",
}

#: Section 18.5's verdicts.
VERDICT: Final[dict[str, str]] = {
    "supported_explanation": "Supported explanation",
    "multiple_plausible_explanations": "Multiple plausible explanations",
    "insufficient_evidence": "Insufficient evidence, no conclusion issued",
}

#: Section 21.4's review actions, from the console design's decision 6.
REVIEW_ACTION: Final[dict[str, str]] = {
    "confirm": "Confirm finding",
    "dismiss": "Dismiss",
    "request_more_evidence": "Request more evidence (re-run)",
    "add_correction": "Add correction",
}

#: What a review does and does not do, shown beside the actions rather than left to inference.
REVIEW_DISCLAIMER: Final[str] = (
    "Reviewing records your judgement of the assessment. It does not authorise any operational "
    "action: this system is read-only and has no actuation path."
)

#: The extraction QC states, from decision 14. Not "auto-accepted", which reads like an operational
#: approval of the kind this system never gives.
EXTRACTION_QC: Final[dict[bool, str]] = {
    False: "High-confidence extraction",
    True: "Needs review",
}

#: Evaluation vocabulary that must not reach an operator screen. Decision 5 names the first three;
#: the rest are the words this project uses about itself and which mean nothing to a reader who did
#: not write the protocol.
ENGINEERING_WORDS: Final[tuple[str, ...]] = (
    "abstained",
    "abstention",
    "success mode",
    "pass mark",
    "hold-out",
    "development split",
    "machine-assisted",
    "vacuous",
    "tautology",
)


def verdict_label(verdict: str) -> str:
    """The operator-facing label, or the raw value if the taxonomy ever grows past this map.

    Returning the raw value rather than raising, because a screen that fails to render is worse
    than one showing a schema name, and the test below catches an unmapped value before release.
    """
    return VERDICT.get(verdict, verdict)


def causal_level_label(level: str | None) -> str:
    return CAUSAL_LEVEL.get(level, level or "Unresolved")


def engineering_words_in(text: str) -> list[str]:
    """Which forbidden words appear in this text, lowercased comparison."""
    lowered = text.lower()
    return [word for word in ENGINEERING_WORDS if word in lowered]
