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
from collections.abc import Mapping, Sequence
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
        value: float,
        unit: str,
        *,
        formula: str,
        inputs: Sequence[AnyFact],
    ) -> DerivedFact:
        """Store a computed quantity, refusing one whose inputs are not already in the ledger.

        Refusing is the point. A derived fact whose inputs are unknown is a number wearing the
        costume of a traceable one.
        """
        if not inputs:
            raise LineageError(f"derived fact {metric!r} has no inputs")
        for parent in inputs:
            if parent.id not in self._facts:
                raise LineageError(f"input {parent.id} is not in the ledger")

        derived = DerivedFact(
            id=self._next_id("derived"),
            metric=metric,
            value=value,
            unit=unit,
            formula=formula,
            input_fact_ids=tuple(p.id for p in inputs),
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
        """Raise unless every step of this fact's lineage resolves to measurements.

        This is the gate a finding has to pass before it can be published.
        """
        roots = self.roots(fact_id)
        if not roots:
            raise LineageError(f"{fact_id} resolves to no measurement")

    def manifest_hash(self) -> str:
        """A stable digest of the whole ledger, for a run manifest.

        Two runs that produce the same facts produce the same digest, so a result can be tied
        to the exact numbers it was computed from rather than to a promise about them.
        """
        digest = hashlib.sha256()
        for key in sorted(self._facts):
            fact = self._facts[key]
            payload: Any = fact.model_dump(mode="json")
            digest.update(repr(sorted(payload.items())).encode())
        return digest.hexdigest()
