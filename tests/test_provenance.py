"""The fact ledger: the gate that stops a number being published without lineage."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from volve_ops.provenance.facts import DerivedFact, Fact, FactLedger, LineageError


def ledger_with_a_shortfall() -> tuple[FactLedger, DerivedFact]:
    led = FactLedger()
    expected = led.record(
        "oil_expected",
        2400.0,
        "Sm3",
        source="expectation.naive-median28",
        locator={"well": "15/9-F-12", "date": "2010-02-01"},
        recorded_at=dt.date(2010, 2, 1),
    )
    actual = led.record(
        "oil_actual",
        1800.0,
        "Sm3",
        source="production.daily",
        locator={"well": "15/9-F-12", "date": "2010-02-01"},
        recorded_at=dt.date(2010, 2, 1),
    )
    shortfall = led.derive(
        "rate_shortfall",
        600.0,
        "Sm3",
        formula="expected - actual",
        inputs=[expected, actual],
    )
    percent = led.derive(
        "shortfall_pct",
        25.0,
        "percent",
        formula="shortfall / expected * 100",
        inputs=[shortfall, expected],
    )
    return led, percent


def test_a_measured_fact_carries_the_locator_that_makes_it_checkable() -> None:
    led = FactLedger()
    fact = led.record(
        "oil_actual",
        1800.0,
        "Sm3",
        source="production.daily",
        locator={"well": "15/9-F-12", "date": "2010-02-01"},
    )
    assert isinstance(fact, Fact)
    assert fact.is_derived is False
    assert fact.source_locator["well"] == "15/9-F-12"


def test_a_derived_fact_resolves_to_the_measurements_under_it() -> None:
    led, percent = ledger_with_a_shortfall()
    roots = led.roots(percent.id)
    assert {r.metric for r in roots} == {"oil_expected", "oil_actual"}
    led.check(percent.id)


def test_a_percentage_is_checkable_without_appearing_in_any_source() -> None:
    """The reason lineage beats string matching: 25.0 appears in no source row."""
    led, percent = ledger_with_a_shortfall()
    assert percent.value == 25.0
    assert all(r.value != 25.0 for r in led.roots(percent.id))
    led.check(percent.id)


def test_deriving_from_a_fact_outside_the_ledger_is_refused() -> None:
    led = FactLedger()
    inside = led.record("a", 1.0, "Sm3", source="s")
    outside = Fact(id="fact_999999", metric="b", value=2.0, unit="Sm3", source="elsewhere")
    with pytest.raises(LineageError, match="not in the ledger"):
        led.derive("c", 3.0, "Sm3", formula="a + b", inputs=[inside, outside])


def test_a_derived_fact_with_no_inputs_is_refused() -> None:
    led = FactLedger()
    with pytest.raises(LineageError, match="no inputs"):
        led.derive("invented", 42.0, "Sm3", formula="trust me", inputs=[])


def test_an_unknown_fact_cannot_be_fetched_or_checked() -> None:
    led = FactLedger()
    with pytest.raises(LineageError, match="no such fact"):
        led.get("fact_000001")


def test_lineage_walks_several_levels_deep() -> None:
    led, percent = ledger_with_a_shortfall()
    chain = led.lineage(percent.id)
    assert len(chain) == 4
    assert sum(1 for f in chain if f.is_derived) == 2


def test_the_ledger_digest_is_stable_and_sensitive() -> None:
    """Same facts, same digest; a different value, a different digest."""
    first, _ = ledger_with_a_shortfall()
    second, _ = ledger_with_a_shortfall()
    assert first.manifest_hash() == second.manifest_hash()

    third, _ = ledger_with_a_shortfall()
    third.record("extra", 1.0, "Sm3", source="s")
    assert third.manifest_hash() != first.manifest_hash()


def test_facts_are_immutable_once_recorded() -> None:
    led = FactLedger()
    fact = led.record("oil_actual", 1800.0, "Sm3", source="production.daily")
    with pytest.raises(ValidationError):
        fact.value = 9999.0  # type: ignore[misc]
