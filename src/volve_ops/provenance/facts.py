"""Facts, derived facts, and the lineage between them.

The design thesis of this project is that the language model never gets to create reality.
This module is where that stops being a slogan: every quantitative claim the system publishes
has to resolve to a Fact measured from a source, or to a DerivedFact computed from other facts
by a stated formula. A number with no lineage cannot be published, however plausible it looks.

Grounding by string matching is deliberately not what happens here. Checking that "2,450"
appears somewhere in a source document would accept a number that happens to collide and
reject every legitimate derived quantity: a percentage, a difference, a unit conversion. Facts
carry their inputs instead, so a derived value is checkable by recomputation rather than by
textual coincidence.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Fact(BaseModel):
    """A measured quantity, traceable to the row it came from.

    The locator is what makes a fact checkable: it says which well, which date, which column
    of which source, so that a reader can go back to the data and find the same number.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    metric: str
    value: float
    unit: str
    source: str
    source_locator: Mapping[str, str] = Field(default_factory=dict)
    recorded_at: dt.date | None = None

    @property
    def is_derived(self) -> bool:
        return False


class DerivedFact(BaseModel):
    """A quantity computed from other facts, by a formula that is written down.

    `input_fact_ids` is not decoration. It is what lets a validator walk from a published claim
    back to measurements, and what lets a reviewer ask why a number is what it is and get an
    answer rather than an assertion.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    metric: str
    value: float
    unit: str
    formula: str
    input_fact_ids: tuple[str, ...]
    combines_units: bool = False
    """Set when the derivation multiplies or divides across units on purpose.

    `check` refuses a derived fact whose inputs disagree on units, because that is how an
    accidental sum of two different quantities gets published. But a product legitimately changes
    units: a volume in Sm3 times a price in USD/Sm3 is USD. Rather than loosen the guard, the
    caller says so here, and the claim is stored where a reader can see it was deliberate.
    """

    @property
    def is_derived(self) -> bool:
        return True


AnyFact = Fact | DerivedFact


class LineageError(Exception):
    """A fact's lineage is broken, so anything resting on it cannot be published."""


class FactLedger:
    """An append-only store of facts with lineage that can be walked and checked.

    Append-only because a published finding that quietly changes the number underneath it is
    worse than one that was wrong in the first place: the first is a mistake, the second is a
    record that cannot be trusted at all.
    """

    def __init__(self) -> None:
        self._facts: dict[str, AnyFact] = {}
        self._counter = 0

    def __len__(self) -> int:
        return len(self._facts)

    def __contains__(self, fact_id: str) -> bool:
        return fact_id in self._facts

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self._counter:06d}"

    def get(self, fact_id: str) -> AnyFact:
        try:
            return self._facts[fact_id]
        except KeyError:
            raise LineageError(f"no such fact: {fact_id}") from None

    def record(
        self,
        metric: str,
        value: float,
        unit: str,
        *,
        source: str,
        locator: Mapping[str, str] | None = None,
        recorded_at: dt.date | None = None,
    ) -> Fact:
        """Store a measured quantity."""
        fact = Fact(
            id=self._next_id("fact"),
            metric=metric,
            value=value,
            unit=unit,
            source=source,
            source_locator=dict(locator or {}),
            recorded_at=recorded_at,
        )
        self._facts[fact.id] = fact
        return fact

    def derive(
        self,
        metric: str,
        unit: str,
        *,
        formula: str,
        inputs: Sequence[AnyFact],
        compute: Callable[..., float],
        combines_units: bool = False,
    ) -> DerivedFact:
        """Compute and store a derived quantity. The value is produced, never asserted.

        The caller supplies the computation rather than its answer. That is the difference
        between a formula that documents a number and one that produces it: a derived fact
        cannot disagree with its own stated derivation, because the derivation is what made it.
        An earlier version took the value as an argument and stored the formula as text beside
        it, which would have accepted `derive("sum", 999999, formula="a + b", inputs=[100, 50])`
        without complaint.

        Inputs must already be in the ledger. A derived fact whose inputs are unknown is a
        number wearing the costume of a traceable one.
        """
        if not inputs:
            raise LineageError(f"derived fact {metric!r} has no inputs")
        for parent in inputs:
            if parent.id not in self._facts:
                raise LineageError(f"input {parent.id} is not in the ledger")

        value = compute(*(p.value for p in inputs))

        derived = DerivedFact(
            id=self._next_id("derived"),
            metric=metric,
            value=value,
            unit=unit,
            formula=formula,
            input_fact_ids=tuple(p.id for p in inputs),
            combines_units=combines_units,
        )
        self._facts[derived.id] = derived
        return derived

    def lineage(self, fact_id: str) -> list[AnyFact]:
        """Every fact reachable from this one, the derived ones first, measurements last."""
        seen: dict[str, AnyFact] = {}
        frontier = [fact_id]
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            fact = self.get(current)
            seen[current] = fact
            if isinstance(fact, DerivedFact):
                frontier.extend(fact.input_fact_ids)
        return list(seen.values())

    def roots(self, fact_id: str) -> list[Fact]:
        """The measurements a claim ultimately rests on."""
        return [f for f in self.lineage(fact_id) if isinstance(f, Fact)]

    def check(self, fact_id: str) -> None:
        """Raise unless this fact's lineage is intact and every unit along it agrees.

        Reaching a measurement is not on its own worth checking: `derive` already refuses
        unknown inputs and the ledger is append-only, so every stored fact reaches one by
        construction. What this does check is that the chain is complete, that no step is
        missing from the store, and that a derived quantity has not silently mixed units,
        which is the realistic way a lineage goes wrong once more than one source feeds it.
        """
        fact = self.get(fact_id)
        roots = self.roots(fact_id)
        if not roots:
            raise LineageError(f"{fact_id} resolves to no measurement")

        for step in self.lineage(fact_id):
            if isinstance(step, DerivedFact):
                for parent_id in step.input_fact_ids:
                    if parent_id not in self._facts:
                        raise LineageError(f"{fact_id}: input {parent_id} of {step.id} is missing")
        if isinstance(fact, DerivedFact) and not fact.combines_units:
            units = {self.get(i).unit for i in fact.input_fact_ids}
            if len(units) > 1 and fact.unit not in {"percent", "ratio", "dimensionless"}:
                raise LineageError(
                    f"{fact_id} is {fact.unit} but its inputs mix {sorted(units)}; "
                    "a derivation across units must say what it produced"
                )

    def manifest_hash(self) -> str:
        """A digest of the ledger's content, for a run manifest.

        Hashed on content rather than on identifiers, and over a canonical ordering, so that two
        runs producing the same facts agree even if they recorded them in a different order.
        Hashing the stored ids instead would make the digest depend on insertion order, since
        ids are issued by a counter, and a digest that changes when nothing of substance did is
        worse than none: it trains the reader to ignore it.
        """

        def canonical(fact: AnyFact) -> str:
            payload: Any = fact.model_dump(mode="json")
            payload.pop("id", None)
            if isinstance(fact, DerivedFact):
                # Replace input ids with the content of what they point at, recursively, so
                # lineage is part of the digest without the ids being part of it.
                payload["input_fact_ids"] = sorted(
                    canonical(self.get(i)) for i in fact.input_fact_ids
                )
            return json.dumps(payload, sort_keys=True, default=str)

        digest = hashlib.sha256()
        for entry in sorted(canonical(f) for f in self._facts.values()):
            digest.update(entry.encode())
        return digest.hexdigest()
