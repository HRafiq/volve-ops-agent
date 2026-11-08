"""The seven provenance-failure classes of protocol section 22.6.

Failure F12 of the design brief, made specific. Each class is an attempt to publish something
the provenance rules forbid, and mark 8 requires that each is **stopped at the gate**, not merely
unconstructible. A test that builds an invalid finding and asserts the constructor refused it has
tested the constructor; what matters is whether a finding that reaches publication is caught.

So every experiment here builds a finding the type system accepts, hands it to the real gate, and
records which rule fired. A class with no rule behind it is reported as unblocked, which is a
result about the gate rather than about the fixture.

Class 3, a figure whose source resolves to a record holding a different value, is why this list
exists in this form. Amendment 11 recorded 198 of 198 drawer figures attributed to facts
recording different numbers, with every source resolving, so every check passed. Resolving is a
weaker property than supporting, and the difference was invisible for an entire phase.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from volve_ops.console.store import RunStore
from volve_ops.investigation.schemas import Finding
from volve_ops.investigation.validator import CitableDocument, GateResult, check
from volve_ops.provenance.facts import FactLedger


@dataclass(frozen=True)
class FailureClass:
    """One way a finding can be wrong about where its figures came from."""

    number: int
    name: str
    what_it_attempts: str
    expected_rule: str
    """The gate rule that must fire. Empty where section 22.6 names a class nothing yet blocks."""


FAILURE_CLASSES: Final[tuple[FailureClass, ...]] = (
    FailureClass(
        1,
        "derived figure with no lineage",
        "publish a derived quantity whose chain reaches no measurement",
        "broken_lineage",
    ),
    FailureClass(
        2,
        "declared source does not resolve",
        "anchor a figure to a fact id the ledger does not hold",
        "fact_not_in_ledger",
    ),
    FailureClass(
        3,
        "source resolves to a different value",
        "anchor a figure to a real fact that records a different number",
        "figure_contradicts_its_record",
    ),
    FailureClass(
        4,
        "quote attributed to the wrong document",
        "cite a span against a document name the index does not hold for that event",
        "document_name_wrong",
    ),
    FailureClass(
        5,
        "cited event does not exist",
        "cite an event id that is not in the event store",
        "document_not_available",
    ),
    FailureClass(
        6,
        "evidence outside the episode window",
        "support a finding with a document dated outside the episode it explains",
        "citation_outside_the_window",
    ),
    FailureClass(
        7,
        "a level with no evidence behind it",
        "claim a documented causal level while disclaiming the document",
        "documented_level_disclaims_itself",
    ),
)


@dataclass(frozen=True)
class Outcome:
    """What the gate did with one attempt."""

    failure_class: FailureClass
    blocked: bool
    rules_fired: tuple[str, ...]
    detail: str

    @property
    def blocked_by_the_expected_rule(self) -> bool:
        return self.failure_class.expected_rule in self.rules_fired


def run_at_the_gate(
    failure_class: FailureClass,
    finding: Finding,
    ledger: FactLedger,
    documents: Mapping[str, CitableDocument],
) -> Outcome:
    """Hand one malformed finding to the real publication gate and record what it did."""
    result: GateResult = check(finding, ledger, documents)
    rules = tuple(v.rule for v in result.violations)
    return Outcome(
        failure_class=failure_class,
        blocked=not result.passed,
        rules_fired=rules,
        detail="; ".join(f"{v.rule}: {v.detail}" for v in result.violations)[:400],
    )


def unblocked(outcomes: Sequence[Outcome]) -> tuple[FailureClass, ...]:
    """Classes the gate let through, which is the result mark 8 is actually about."""
    return tuple(o.failure_class for o in outcomes if not o.blocked_by_the_expected_rule)


# --------------------------------------------------------------------------------------------
# class 3, which lives at a different gate from the other six
# --------------------------------------------------------------------------------------------
#
# A `Finding` carries fact **ids**, not figures, so there is no number in it that could contradict
# a record. The figures are in the console payloads, which is exactly where amendment 11 found the
# defect: 198 of 198 drawer figures attributed to facts recording different numbers, every source
# resolving, every check passing.
#
# So class 3 is checked against the assembled payloads rather than at the investigation gate. It
# is not a ninth mark of section 21.6: amendment 7 records what happens when a gate is invented
# after the fact, and this one was pre-registered in section 22.6 and pushed as prereg-v16 before
# any of it was written.

#: Relative tolerance when comparing a published figure with the value its fact records. Section
#: 21.1 permits rounding for display and requires the unrounded value in the payload, so this is
#: float-representation slack and not a display allowance. A figure rounded into the payload would
#: be a section 21.1 violation on its own.
VALUE_TOLERANCE: Final[float] = 1e-9


@dataclass(frozen=True)
class Contradiction:
    """A published figure that does not equal the record it names."""

    payload: str
    path: str
    source: str
    published: float
    recorded: float

    def __str__(self) -> str:
        return (
            f"{self.payload}: {self.path} publishes {self.published!r} sourced to {self.source}, "
            f"which records {self.recorded!r}"
        )


def figures_contradicting_their_records(
    payloads: Mapping[str, object], fact_values: Mapping[str, float]
) -> tuple[Contradiction, ...]:
    """Every published figure whose declared fact records a different number.

    `fact_values` maps a fact id to the value the provenance ledger holds for it, read from the
    published facts artifacts rather than recomputed. A figure sourced to something that is not a
    fact id is not this check's business: mark 1 already requires every source to resolve, and
    resolving is what that check is for. This one asks the question mark 1 cannot: not whether the
    source exists, but whether it says what the figure claims it says.

    **Fact ids restart at `fact_000001` for every episode**, so `fact_values` must hold the facts
    of the one episode these payloads belong to and no other. Prefer `contradictions_in_console`,
    which does that scoping itself. The first run of this check built one map across every episode
    and reported 183 contradictions, all of them comparisons between one episode's figure and
    another's record. The console was right and the check was wrong, which is the third time in
    this project a verification script has produced a false finding by indexing one thing against
    another, so the safe entry point exists and this one says why.
    """
    from volve_ops.console.sources import Sourced

    found: list[Contradiction] = []

    def walk(node: object, path: str, payload_name: str) -> None:
        if isinstance(node, Sourced):
            recorded = fact_values.get(node.source)
            if recorded is not None and isinstance(node.value, int | float):
                published = float(node.value)
                if not _close(published, recorded):
                    found.append(
                        Contradiction(
                            payload=payload_name,
                            path=path or "(root)",
                            source=node.source,
                            published=published,
                            recorded=recorded,
                        )
                    )
            walk(node.value, f"{path}.value", payload_name)
            return
        if hasattr(node, "model_fields"):
            for field in type(node).model_fields:
                walk(getattr(node, field), f"{path}.{field}" if path else field, payload_name)
            return
        if isinstance(node, Mapping):
            for key, value in node.items():
                walk(value, f"{path}.{key}", payload_name)
            return
        if isinstance(node, list | tuple):
            for index, value in enumerate(node):
                walk(value, f"{path}.{index}", payload_name)

    for name, payload in payloads.items():
        walk(payload, "", name)
    return tuple(found)


def _close(published: float, recorded: float) -> bool:
    if published == recorded:
        return True
    scale = max(abs(published), abs(recorded), 1.0)
    return abs(published - recorded) <= VALUE_TOLERANCE * scale


def contradictions_in_console(store: RunStore) -> tuple[Contradiction, ...]:
    """Class 3 over the whole console, with each payload judged against its own episode's facts.

    The safe entry point. Fact ids are per-episode, so a single map across the cache compares
    figures with records that have nothing to do with them.
    """
    from volve_ops.console import assemble

    found: list[Contradiction] = []
    queue = assemble.queue(store)
    for row in queue.rows:
        record = store.by_id(row.investigation_id)
        artifacts = store.artifacts_for(str(record["well"]), str(record["onset"]))
        fact_values = {str(f["id"]): float(f["value"]) for f in artifacts.facts}
        payload = assemble.detail(store, row.investigation_id)
        found.extend(
            figures_contradicting_their_records({row.investigation_id: payload}, fact_values)
        )
    return tuple(found)
