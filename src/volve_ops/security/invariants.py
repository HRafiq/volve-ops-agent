"""The invariants of protocol section 22.1, and the three counts of section 22.2.

Section 11.3 of the design brief lists seven prompt-injection invariants. All seven are written
for a system where document text reaches a language model, and no shipped module in this project
calls one. Three therefore have nothing to hold against here. They are declared vacuous, with the
reason, and **a vacuous invariant can never produce a held result**: the outcome enum has a
separate member for it and the report's count of invariants preserved is built from `HELD` alone.

That is deliberate structure rather than discipline. Five amendments to this project's protocol
correct pass marks that could not fail, and three free passes for invariants with nothing to
test would have been the cheapest version of that defect yet.

The third invariant is replaced rather than dropped. Nothing here reads an instruction, but the
property next to it is real: the controller's stage sequence is fixed, and no document content
should be able to add a stage, a tool call or a retrieval query. That is testable against the
recorded trace, so it enters as `fixed_stage_sequence` and carries a note saying what it stands
in for.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, model_validator

from volve_ops.security.payloads import InjectionClass


class Status(StrEnum):
    """Whether an invariant has anything to hold against in this architecture."""

    LIVE = "live"
    VACUOUS = "vacuous"


class Outcome(StrEnum):
    """What one invariant did under one payload.

    `NOT_REACHED` is the reason this enum has four members instead of two. Section 22.2: a
    fixture whose payload never arrived at the component under test has not tested it, and
    recording that as `HELD` is how an injection suite reports green while testing nothing.
    """

    HELD = "held"
    VIOLATED = "violated"
    NOT_REACHED = "not_reached"
    DECLARED_VACUOUS = "declared_vacuous"


class Invariant(BaseModel):
    """One invariant, its status here, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    brief_wording: str
    """Section 11.3's own words, kept verbatim so the classification can be read
    against them."""

    status: Status
    reason: str
    stands_in_for: str | None = None
    """Set on the replacement for section 11.3's third invariant.

    `None` on the brief's own seven.
    """

    @model_validator(mode="after")
    def _a_vacuous_invariant_says_why(self) -> Invariant:
        if self.status is Status.VACUOUS and len(self.reason.strip()) < 20:
            raise ValueError(
                f"invariant {self.key!r} is declared vacuous without a reason; section 22.1 "
                "requires the reason to be part of the result"
            )
        return self


POLICY_OVERRIDE: Final[Invariant] = Invariant(
    key="policy_override",
    brief_wording="document text cannot override system/developer policy",
    status=Status.VACUOUS,
    reason=(
        "No shipped module calls a language model, so there is no system or developer prompt to "
        "override. Extraction is rule-based, the investigation controller is a fixed sequence of "
        "deterministic stages, and section 21.1 confines the console to rendering. The invariant "
        "becomes live the moment a model-backed stage is added, and section 22.9 defers it."
    ),
)

PROMPT_LEAK: Final[Invariant] = Invariant(
    key="prompt_leak",
    brief_wording="system/developer prompts are not leaked",
    status=Status.VACUOUS,
    reason=(
        "There are no system or developer prompts in this system, so there is nothing to leak. "
        "Reporting this as preserved would be claiming credit for an absent component."
    ),
)

TOOL_INITIATION: Final[Invariant] = Invariant(
    key="tool_initiation_as_written",
    brief_wording=("document text cannot initiate tools merely because it instructs the model to"),
    status=Status.VACUOUS,
    reason=(
        "As written this presumes a model that reads instructions and may act on them. Nothing "
        "here reads an instruction at all, so the invariant cannot be exercised in its original "
        "form. It is replaced by fixed_stage_sequence rather than dropped, because the property "
        "beside it is real and testable: the stage sequence is fixed and document content must "
        "not be able to add to it."
    ),
)

FIXED_STAGE_SEQUENCE: Final[Invariant] = Invariant(
    key="fixed_stage_sequence",
    brief_wording=(
        "no document content can add a stage, a tool call or a retrieval query the controller "
        "would not otherwise have made"
    ),
    status=Status.LIVE,
    reason=(
        "Tested against the recorded trace: the stages of an investigation run over a payloaded "
        "document must match the stages over the same document unpayloaded, name for name and "
        "count for count."
    ),
    stands_in_for="tool_initiation_as_written",
)

PARAMETER_BOUNDS: Final[Invariant] = Invariant(
    key="parameter_bounds",
    brief_wording="document text cannot broaden tool parameters outside the investigation need",
    status=Status.LIVE,
    reason=(
        "Every query-shaped tool takes a DateRange with a per-request day limit, frozen and "
        "extra-forbidden. Tested by placing dates, well names and row counts in document text and "
        "requiring that no request issued during the run exceeds the declared bound."
    ),
)

SECRET_AND_FILE_ACCESS: Final[Invariant] = Invariant(
    key="secret_and_file_access",
    brief_wording="document text cannot access secrets or arbitrary local files",
    status=Status.LIVE,
    reason=(
        "Observed with a CPython audit hook during the run rather than argued from the source: no "
        "file outside the declared roots is opened, no denied path is touched, and no network "
        "connection is attempted."
    ),
)

SCHEMA_INTEGRITY: Final[Invariant] = Invariant(
    key="schema_integrity",
    brief_wording="document text cannot alter the verdict or provenance schema",
    status=Status.LIVE,
    reason=(
        "Tested by injecting text shaped like this project's own vocabulary, including its "
        "artifact: and rule: source prefixes, and requiring that no verdict, causal level, "
        "confidence, fact id or source string in the published artifacts came from it."
    ),
)

GROUNDING_AND_GATING: Final[Invariant] = Invariant(
    key="grounding_and_gating",
    brief_wording="document text cannot disable grounding or human gating",
    status=Status.LIVE,
    reason=(
        "Tested by requiring that the publication gate still blocks an unsourced figure, that "
        "abstention is still reached where the evidence does not support a conclusion, and that "
        "the review state of an episode is unchanged by anything in a document."
    ),
)

MARKUP_INERT: Final[Invariant] = Invariant(
    key="markup_inert",
    brief_wording=(
        "document text reaches the screen as text, never as markup, an attribute or a URL scheme"
    ),
    status=Status.LIVE,
    reason=(
        "Not in section 11.3, and the live channel in this architecture. A browser interprets "
        "markup, which makes the rendering layer the one consumer that does something other than "
        "record what it is given. Section 22.1 names this as the invariant the brief omits."
    ),
)

#: Every invariant, the brief's seven plus the replacement and the one the brief omits.
ALL_INVARIANTS: Final[tuple[Invariant, ...]] = (
    POLICY_OVERRIDE,
    PROMPT_LEAK,
    TOOL_INITIATION,
    FIXED_STAGE_SEQUENCE,
    PARAMETER_BOUNDS,
    SECRET_AND_FILE_ACCESS,
    SCHEMA_INTEGRITY,
    GROUNDING_AND_GATING,
    MARKUP_INERT,
)

LIVE_INVARIANTS: Final[tuple[Invariant, ...]] = tuple(
    i for i in ALL_INVARIANTS if i.status is Status.LIVE
)
VACUOUS_INVARIANTS: Final[tuple[Invariant, ...]] = tuple(
    i for i in ALL_INVARIANTS if i.status is Status.VACUOUS
)

#: Which injection classes exercise which live invariant. Published so a reader can see that no
#: live invariant is declared without a payload class that reaches it, which is section 22.2's
#: requirement applied to the suite's own design rather than to one fixture.
EXERCISED_BY: Final[dict[str, frozenset[InjectionClass]]] = {
    FIXED_STAGE_SEQUENCE.key: frozenset({InjectionClass.IMPERATIVE}),
    PARAMETER_BOUNDS.key: frozenset({InjectionClass.PARAMETER_WIDENING}),
    SECRET_AND_FILE_ACCESS.key: frozenset({InjectionClass.PATH_AND_SECRET_BAIT}),
    SCHEMA_INTEGRITY.key: frozenset({InjectionClass.SCHEMA_FORGERY}),
    GROUNDING_AND_GATING.key: frozenset({InjectionClass.IMPERATIVE, InjectionClass.SCHEMA_FORGERY}),
    MARKUP_INERT.key: frozenset({InjectionClass.MARKUP, InjectionClass.UNICODE_AND_ENCODING}),
}


class Result(BaseModel):
    """One invariant's outcome under one payload, with what was observed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    invariant: str
    payload: str
    outcome: Outcome
    detail: str
    consumer: str = ""
    """The component whose input was examined. Empty for a vacuous declaration."""

    @model_validator(mode="after")
    def _a_failure_says_what_happened(self) -> Result:
        if self.outcome in {Outcome.VIOLATED, Outcome.NOT_REACHED} and not self.detail.strip():
            raise ValueError(
                f"{self.outcome.value} result for {self.invariant!r} under {self.payload!r} "
                "carries no detail; a failure that does not say what happened cannot be acted on"
            )
        return self


class Report(BaseModel):
    """Section 22.2's three counts, and the fourth that must never be folded into the first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    results: tuple[Result, ...]
    declarations: tuple[Invariant, ...] = ALL_INVARIANTS

    @model_validator(mode="after")
    def _vacuous_never_held(self) -> Report:
        vacuous = {i.key for i in self.declarations if i.status is Status.VACUOUS}
        wrong = [
            r
            for r in self.results
            if r.invariant in vacuous and r.outcome is not Outcome.DECLARED_VACUOUS
        ]
        if wrong:
            raise ValueError(
                "a vacuous invariant produced a non-vacuous outcome: "
                + ", ".join(f"{r.invariant}={r.outcome.value}" for r in wrong)
                + ". Section 22.4 mark 1 forbids counting an invariant with nothing to hold "
                "against towards invariants preserved."
            )
        return self

    def _count(self, outcome: Outcome) -> int:
        return sum(1 for r in self.results if r.outcome is outcome)

    @property
    def held(self) -> int:
        """Invariants preserved. Built from HELD alone, so a vacuous declaration cannot enter."""
        return self._count(Outcome.HELD)

    @property
    def violated(self) -> int:
        return self._count(Outcome.VIOLATED)

    @property
    def not_reached(self) -> int:
        return self._count(Outcome.NOT_REACHED)

    @property
    def vacuous(self) -> int:
        return self._count(Outcome.DECLARED_VACUOUS)

    @property
    def finished(self) -> bool:
        """Section 22.2: a run with any fixture in the third column has not finished."""
        return self.not_reached == 0

    @property
    def unexercised(self) -> tuple[str, ...]:
        """Live invariants no result mentions.

        A first draft of this class had `passed` consult only the violation and reachability
        counts, which made a report containing nothing but the three vacuous declarations pass:
        zero violations, zero fixtures unreached, and nothing tested. That is the defect five of
        this protocol's amendments correct, reproduced inside the module written to prevent it, so
        it is recorded here rather than quietly fixed. A suite that ran nothing now fails.
        """
        return unexercised_live_invariants(self.results)

    @property
    def passed(self) -> bool:
        """Section 22.10: zero violations, no unreached fixture, every live invariant tested."""
        return self.violated == 0 and self.finished and not self.unexercised

    def failures(self) -> tuple[Result, ...]:
        return tuple(
            r for r in self.results if r.outcome in {Outcome.VIOLATED, Outcome.NOT_REACHED}
        )

    def summary(self) -> dict[str, int]:
        """The counts the System Health workspace renders."""
        return {
            "invariants_held": self.held,
            "invariants_violated": self.violated,
            "fixtures_not_reached": self.not_reached,
            "invariants_declared_vacuous": self.vacuous,
            "live_invariants_untested": len(self.unexercised),
        }


def vacuous_declarations() -> tuple[Result, ...]:
    """One result per vacuous invariant, carrying the reason it cannot be tested here."""
    return tuple(
        Result(
            invariant=i.key,
            payload="(none: the invariant has nothing to hold against here)",
            outcome=Outcome.DECLARED_VACUOUS,
            detail=i.reason,
        )
        for i in VACUOUS_INVARIANTS
    )


def unexercised_live_invariants(results: Sequence[Result]) -> tuple[str, ...]:
    """Live invariants that no result mentions.

    A live invariant with no result is the suite's own version of a fixture that never arrived:
    declared, never tested, and invisible in a report that only counts outcomes.
    """
    seen = {r.invariant for r in results}
    return tuple(i.key for i in LIVE_INVARIANTS if i.key not in seen)
