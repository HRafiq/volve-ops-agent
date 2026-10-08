"""The investigation queue's priority rule, fixed in protocol section 21.5 and ADR 0009.

Deterministic, printed wherever the queue is printed, and never decided by a model. A queue ordered
by a language model's sense of importance is the failure this project exists to avoid.

ADR 0009 is the honest account of what this rule is worth, and it is worth repeating here because
the rule's shape flatters it. Four terms, of which **two fire on nothing in a first run**: review is
pending for no episode until an operator creates a review, and the unresolved term is scoped to the
cases where the evidence was good enough to choose and the system still did not. On the fourteen
development episodes the rule therefore reduces to shortfall plus duration, and the clause the
console design left open changes the band of none of them.

So `term_counts` is part of the output rather than a diagnostic. A rubric with four lines that
behaves like two is more persuasive than it deserves to be, and the only fix is to publish how often
each line fires next to the scores it produced.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict

#: Section 21.5's thresholds. Fixed before the queue rendered anything, and exempt from the
#: convenience of discovering that a slightly different cut-off would have produced a tidier spread.
#: Tuning them against fourteen episodes would be fitting a priority rule to fourteen cases.
LARGE_SHORTFALL_SM3: Final[float] = 30_000.0
MODERATE_SHORTFALL_SM3: Final[float] = 10_000.0
LONG_EPISODE_DAYS: Final[int] = 40
HIGH_SCORE: Final[int] = 5
MEDIUM_SCORE: Final[int] = 3

#: The evidence bands in which an unresolved verdict raises priority. ADR 0009: a case where the
#: evidence was strong and the system still could not choose is where a human adds the most. "No
#: evidence, so no conclusion" is a data-coverage problem and belongs in a filter, not at the top of
#: a review queue.
ATTENTION_BANDS: Final[frozenset[str]] = frozenset({"high", "moderate"})

#: The one verdict that counts as a single supported explanation.
SUPPORTED: Final[str] = "supported_explanation"

#: Review states that leave a human action outstanding.
PENDING_REVIEW: Final[frozenset[str]] = frozenset({"awaiting_review", "rerun_requested"})


class Priority(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Term(StrEnum):
    """The four terms, named so the count of what each fires on can be published."""

    SHORTFALL = "cumulative shortfall"
    DURATION = "episode lasts 40 days or more"
    REVIEW_PENDING = "review is pending"
    UNRESOLVED_WITH_EVIDENCE = (
        "no single explanation supported, and the evidence band is high or moderate"
    )


class Scored(BaseModel):
    """One episode's priority, with the arithmetic that produced it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    well: str
    onset: str
    score: int
    priority: Priority
    shortfall_points: int
    terms_fired: tuple[Term, ...]

    @property
    def explanation(self) -> str:
        """The row's own score, in the words the rule is printed in."""
        fired = ", ".join(t.value for t in self.terms_fired) or "no term beyond shortfall"
        return f"{self.score} = shortfall {self.shortfall_points}, plus: {fired}"


def shortfall_points(cumulative_shortfall_sm3: float) -> int:
    """Section 21.5's three levels. The only term with more than one level."""
    if cumulative_shortfall_sm3 >= LARGE_SHORTFALL_SM3:
        return 3
    if cumulative_shortfall_sm3 >= MODERATE_SHORTFALL_SM3:
        return 2
    return 1


def band_of(score: int) -> Priority:
    if score >= HIGH_SCORE:
        return Priority.HIGH
    if score >= MEDIUM_SCORE:
        return Priority.MEDIUM
    return Priority.LOW


def score_episode(
    *,
    well: str,
    onset: str,
    cumulative_shortfall_sm3: float,
    episode_days: int,
    verdict: str,
    evidence_band: str,
    review_state: str,
) -> Scored:
    """Apply section 21.5's rule to one episode.

    Every input is a figure a manifest already carries. Nothing here reads the production data or
    recomputes a shortfall: section 21.1 confines the console to rendering, and a priority rule that
    derived its own inputs would be the second implementation that section warns about.
    """
    points = shortfall_points(cumulative_shortfall_sm3)
    fired: list[Term] = []
    if episode_days >= LONG_EPISODE_DAYS:
        fired.append(Term.DURATION)
    if review_state in PENDING_REVIEW:
        fired.append(Term.REVIEW_PENDING)
    if verdict != SUPPORTED and evidence_band in ATTENTION_BANDS:
        fired.append(Term.UNRESOLVED_WITH_EVIDENCE)
    total = points + len(fired)
    return Scored(
        well=well,
        onset=onset,
        score=total,
        priority=band_of(total),
        shortfall_points=points,
        terms_fired=tuple(fired),
    )


def term_counts(scored: Sequence[Scored]) -> dict[str, int]:
    """How many episodes each term fired on, published alongside the scores.

    Section 21.5 requires this and ADR 0009 says why: two of the four terms fire on nothing in a
    first run, so a reader shown only the rubric would credit it with judgement it has not made.
    """
    counts = {term.value: 0 for term in Term}
    counts[Term.SHORTFALL.value] = len(scored)
    for row in scored:
        for term in row.terms_fired:
            counts[term.value] += 1
    return counts
