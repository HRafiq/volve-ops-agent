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
from typing import Any, Final

from volve_ops.console.store import RunStore, missing_manifests
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


@dataclass(frozen=True)
class ComparisonResult:
    """What class 3 found, and how many figures it actually compared to find it.

    The denominator is the point. Marks 2 and 13 both refuse a clean result over an empty set, and
    `gates.py` opens by saying a gate that passed over nothing has demonstrated nothing. Mark 8
    published `class_3_contradictions: 0` with no count beside it, so an empty queue produced a
    reported-clean run over zero figures.
    """

    contradictions: tuple[Contradiction, ...]
    compared: int

    @property
    def vacuous(self) -> bool:
        return self.compared == 0


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
    compared: list[int] = []

    def walk(node: object, path: str, payload_name: str) -> None:
        if isinstance(node, Sourced):
            recorded = fact_values.get(node.source)
            # `bool` before `int|float`: a boolean is an int in Python, and a published flag
            # should be compared against the 1.0/0.0 the manifest walk records for it.
            if recorded is not None and isinstance(node.value, bool | int | float):
                compared.append(1)
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
    _LAST_COMPARED.clear()
    _LAST_COMPARED.append(len(compared))
    return tuple(found)


#: How many figures the last call to `figures_contradicting_their_records` actually compared.
#: Module state rather than a changed return type, so the primitive keeps its shape for the tests
#: that pin it; `compare_figures` is the entry point that returns both.
_LAST_COMPARED: list[int] = [0]


def compare_figures(
    payloads: Mapping[str, object], fact_values: Mapping[str, float]
) -> ComparisonResult:
    """`figures_contradicting_their_records` with the denominator beside the result."""
    found = figures_contradicting_their_records(payloads, fact_values)
    return ComparisonResult(contradictions=found, compared=_LAST_COMPARED[0])


def _close(published: float, recorded: float) -> bool:
    if published == recorded:
        return True
    scale = max(abs(published), abs(recorded), 1.0)
    return abs(published - recorded) <= VALUE_TOLERANCE * scale


def manifest_values(manifests: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    """Every numeric leaf in every manifest, keyed by the source string that names it.

    Mark 1 and mark 11 both ask whether a source **resolves**, which for a dotted manifest path
    means only that the key exists. That is the weaker of the two questions, and amendment 11
    recorded what the weaker question misses: 198 of 198 drawer figures attributed to facts
    recording different numbers, every source resolving, every check passing.

    **Lists are walked, with the index as a segment.** The first version of this walk handled
    mappings and scalars and nothing else, so it collected 221 of the 768 numeric leaves in the
    eight manifests, and every figure sourced to a path running through a list was skipped as
    "not a fact we hold" rather than compared. On the health screen that was all seven derived
    figures and none of the literal reads: the check could see only the figures that could not be
    wrong. Independent review found it in the commit that introduced it, which makes this the
    third time this project has shipped an existence check where it needed a value check.

    Booleans are collected as 0.0 and 1.0 so a flipped flag is a contradiction rather than an
    uncompared value. `bool` is a subclass of `int`, so the order of these branches matters.
    """
    found: dict[str, float] = {}

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                walk(value, f"{prefix}.{key}" if prefix else str(key))
            return
        if isinstance(node, list | tuple):
            for index, value in enumerate(node):
                walk(value, f"{prefix}.{index}")
            return
        if isinstance(node, bool):
            found[prefix] = 1.0 if node else 0.0
            return
        if isinstance(node, int | float):
            found[prefix] = float(node)

    for name, manifest in manifests.items():
        walk(manifest, name)
    # One known gap, stated rather than left to be discovered: a manifest key whose own name
    # contains a dot produces a path this walk cannot distinguish from a nested one. `locate`,
    # which `resolve_source` uses, handles that case. Fifteen such keys exist today and all hold
    # booleans under `pass_marks`; a figure sourced to one would be compared against the wrong
    # node or not at all.
    return found


def contradictions_in_health(
    health: object, manifests: Mapping[str, Mapping[str, Any]]
) -> tuple[Contradiction, ...]:
    """Class 3 over the System Health workspace, against the manifests its figures name."""
    return figures_contradicting_their_records(
        {"system_health": health}, manifest_values(manifests)
    )


def contradictions_in_console(store: RunStore) -> ComparisonResult:
    """Class 3 over the whole console, with each payload judged against its own episode's facts.

    The safe entry point. Fact ids are per-episode, so a single map across the cache compares
    figures with records that have nothing to do with them.
    """
    from volve_ops.console import assemble

    found: list[Contradiction] = []
    compared = 0
    queue = assemble.queue(store)
    for row in queue.rows:
        record = store.by_id(row.investigation_id)
        artifacts = store.artifacts_for(str(record["well"]), str(record["onset"]))
        fact_values = {str(f["id"]): float(f["value"]) for f in artifacts.facts}
        payload = assemble.detail(store, row.investigation_id)
        result = compare_figures({row.investigation_id: payload}, fact_values)
        found.extend(result.contradictions)
        compared += result.compared

    # The health screen is NOT walked here. It is a separate question with a separate answer, in
    # `health_contradictions`, because whether it can be walked depends on files this function
    # must still run without.
    #
    # The denominator is this half's, and it is the half that can go to zero: an empty queue walks
    # no payload at all. Mark 8's first vacuity guard watched the **health** half, whose count is
    # structurally fixed by the screen's own shape, so a run over an empty queue still reported
    # clean. 198 figures on real data, 0 on an empty one, and only one of those is a result.
    return ComparisonResult(contradictions=tuple(found), compared=compared)


def health_contradictions(store: RunStore) -> tuple[ComparisonResult, bool]:
    """Class 3 over the System Health screen, and whether it could run at all.

    Its own function with its own flag, rather than a second half of the per-episode check. The
    first version appended it inside `contradictions_in_console` under a
    `contextlib.suppress(ArtifactMissing)`, so the per-episode half could still run without the
    section 22 manifests. That hid two real failures: a first-ever run, where no prior
    `security_run.json` exists, reported one `class_3_ran: true` covering a half that had been
    skipped; and `_episodes_opened_by_selected` raising `ArtifactMissing` when the selected model
    has no row in the ablation manifest, which is itself a figure sourced to something that does
    not exist and was being eaten by the same handler.

    Whether this can run is a question about files, asked here. Anything raised after that is a
    failure and reaches the caller.
    """
    from volve_ops.console import assemble

    if missing_manifests(store.cache):
        return ComparisonResult(contradictions=(), compared=0), False
    result = compare_figures(
        {"system_health": assemble.system_health(store)},
        manifest_values(store.health_manifests()),
    )
    return result, True
