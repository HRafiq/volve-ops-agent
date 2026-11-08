"""The TypeScript interfaces against the Pydantic payloads they are meant to mirror.

**Nothing checked this, and a crash shipped because of it.** Protocol amendment 11 restructured
`FactEvidence`, the frontend's declaration was never updated, and `Drawer.tsx` called
`.join()` on a field the API had stopped serving. React unmounted the whole tree: clicking any
fact-backed evidence cell turned the console into a blank white page, on all fourteen screens.

Every check passed over it. `tsc --noEmit` verifies the frontend against its **own** declaration
and never against the payload. `mypy` verifies the payload and never against the frontend. The
section 21.6 gates read Python objects. `check_like_ci.sh` runs all of them. A contract with two
halves and no test between them is not a contract, and the feature it broke was the one the
amendment was about.

This parses `frontend/src/types.ts` and compares field names, which is the part that drifts. Types
are not compared: TypeScript's and Pydantic's type languages do not line up field for field, and a
check that tried would either be noisy or would quietly weaken to nothing. Names catch the failure
that actually happened.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest
from pydantic import BaseModel

from volve_ops.console import payloads, sources

TYPES_TS: Final[Path] = Path("frontend/src/types.ts")

#: Payload models the console renders, by the TypeScript interface that mirrors each.
#:
#: Listed rather than discovered, so that adding a payload model without a frontend declaration is
#: a decision someone makes here rather than something that happens.
MIRRORED: Final[dict[str, type[BaseModel]]] = {
    "Sourced": sources.Sourced,
    "Money": payloads.Money,
    "Kpi": payloads.Kpi,
    "QueueRow": payloads.QueueRow,
    "PriorityRule": payloads.PriorityRule,
    "Queue": payloads.Queue,
    "Header": payloads.Header,
    "SeriesRow": payloads.SeriesRow,
    "ChartSeries": payloads.ChartSeries,
    "LedgerFact": payloads.LedgerFact,
    "FactEvidence": payloads.FactEvidence,
    "DocumentEvidence": payloads.DocumentEvidence,
    "Absence": payloads.Absence,
    "MatrixCell": payloads.MatrixCell,
    "Hypothesis": payloads.Hypothesis,
    "EvidenceCoverage": payloads.EvidenceCoverage,
    "ExpectationPanel": payloads.ExpectationPanel,
    "InvestigationDetail": payloads.InvestigationDetail,
}

_INTERFACE = re.compile(r"export interface (\w+) \{(.*?)\n\}", re.DOTALL)
_FIELD = re.compile(r"^\s{2}(\w+)\??:", re.MULTILINE)


def declared_interfaces() -> dict[str, set[str]]:
    """Field names per interface, from the TypeScript source."""
    source = TYPES_TS.read_text(encoding="utf-8")
    return {name: set(_FIELD.findall(body)) for name, body in _INTERFACE.findall(source)}


@pytest.mark.skipif(not TYPES_TS.exists(), reason="needs the frontend source")
class TestTheFrontendMirrorsThePayloads:
    def test_every_mirrored_model_has_an_interface(self) -> None:
        declared = declared_interfaces()
        missing = sorted(name for name in MIRRORED if name not in declared)
        assert not missing, f"no TypeScript interface for {missing}"

    @pytest.mark.parametrize("name", sorted(MIRRORED))
    def test_the_field_names_agree(self, name: str) -> None:
        """The check that would have caught the blank page.

        `FactEvidence` lost `fact_id`, `input_records` and `derived_facts` and gained `reference`,
        `value` and `ledger_facts`. The interface kept the old three, and the component read one of
        them off an object that no longer had it.
        """
        declared = declared_interfaces()[name]
        model = set(MIRRORED[name].model_fields)
        assert declared == model, (
            f"{name}: the API serves {sorted(model - declared)} that TypeScript does not declare, "
            f"and TypeScript declares {sorted(declared - model)} that the API does not serve"
        )

    def test_a_component_reading_a_dropped_field_is_what_this_catches(self) -> None:
        """Stated as a case so the test's purpose survives a future reader.

        `SourcedTable`'s own two fields are part of `ChartSeries` through inheritance, and
        `model_fields` includes inherited ones, so the interface has to declare them too. That is
        correct: the frontend receives them on the wire.
        """
        assert "source" in payloads.ChartSeries.model_fields
        assert "row_count" in payloads.ChartSeries.model_fields
        assert {"source", "row_count"} <= declared_interfaces()["ChartSeries"]
