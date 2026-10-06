"""The development results table of protocol section 19.3.

One table, every measured figure in the project, and every row carrying three things beyond its
value: the denominator, because `docs/data_profile.md` has already produced a figure that differs by
two points depending on the population it is taken over; the status, one of `gated`, `reported` or
`deferred`; and for a deferred row, what would settle it.

**The gate is the interesting part.** Section 19.3 requires every published figure to appear here,
and checks it against the run manifests rather than by reading the documents. So the table is
declared as data below, and `uncovered` walks each manifest for a numeric leaf that no row addresses
and no declared prefix excuses. Adding a figure to a manifest without adding a row here fails the
check, which is the only version of this discipline that survives someone being in a hurry.

The excluded prefixes are listed rather than pattern-matched, because an exclusion that a reader
cannot enumerate is a hole.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict


class Status(StrEnum):
    GATED = "gated"
    REPORTED = "reported"
    DEFERRED = "deferred"


class MetricRow(BaseModel):
    """One row. `key` is a dotted path into the named manifest, or None for a deferred row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    layer: str
    metric: str
    manifest: str | None
    key: str | None
    denominator: str
    status: Status
    settled_by: str | None = None
    note: str | None = None

    value: Any = None

    @property
    def rendered(self) -> str:
        if self.status is Status.DEFERRED:
            return "deferred"
        if self.value is None:
            return "not produced"
        if isinstance(self.value, bool):
            return "pass" if self.value else "FAIL"
        if isinstance(self.value, float):
            return f"{self.value:.4f}".rstrip("0").rstrip(".")
        return str(self.value)


#: The four manifests the project's scripts write, by the name rows refer to them by.
MANIFESTS: Final[dict[str, str]] = {
    "expectation": "run_manifest.json",
    "extraction": "extraction_run.json",
    "labels": "label_scoring_run.json",
    "investigation": "investigation_run.json",
}

#: Manifest paths excused from needing a table row. Independent review found the first version
#: excusing 87 of 131 numeric leaves, including the project's headline WAPE table, the label
#: distribution the README calls "the most important figure here", and `investigation.pass_marks` —
#: so a reviewer injected a **failing** pass mark under that prefix and the gate certified full
#: coverage. Section 19.3's claim was false, and false on the accuracy metric.
#:
#: What remains is version strings, identifier lists, per-class breakdowns the table carries in
#: aggregate, and the per-finding rows the investigation table summarises. Nothing here is a figure
#: a document quotes.
#:
#: Prefixes, not exact paths, for the two that are genuinely open vocabularies: `per_subcategory`
#: spans twenty activity subcategories and `per_class` the taxonomy. Everywhere else a new sub-key
#: now needs a new row, which is the point.
EXCLUDED_PREFIXES: Final[tuple[str, ...]] = (
    "expectation.generated",
    "expectation.commit_sha",
    "expectation.dataset_version",
    "expectation.parser_version",
    "expectation.protocol_version",
    "expectation.split",
    "expectation.horizons",
    "expectation.candidates",
    "expectation.selected_model",
    "expectation.fitted_day_dates",
    "extraction.store_version",
    "extraction.content_hash",
    "extraction.parser_version",
    "extraction.extractor_version",
    "extraction.protocol_version",
    "extraction.development_sample.seed",
    "extraction.development_sample.split",
    "extraction.development_sample.event_ids",
    "extraction.development_sample.per_subcategory",
    "extraction.hold_out_sample.seed",
    "extraction.hold_out_sample.split",
    "extraction.hold_out_sample.event_ids",
    "extraction.hold_out_sample.per_subcategory",
    "labels.protocol_version",
    "labels.labels",
    "labels.label_provenance",
    "labels.baselines.echo-subcategory.per_class",
    "labels.baselines.echo-statedetail.per_class",
    "labels.section_14_3.findings",
    "investigation.protocol_version",
    "investigation.development_wells",
    "investigation.bundle_day_dates",
    "investigation.baseline",
    "investigation.findings",
)


def _leaves(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.extend(_leaves(value, f"{prefix}{key}."))
    elif isinstance(obj, list):
        out.append((prefix.rstrip("."), obj))
    else:
        out.append((prefix.rstrip("."), obj))
    return out


def resolve(manifest: Mapping[str, Any], key: str) -> Any:
    """Follow a dotted path, returning None where any step is absent."""
    current: Any = manifest
    for part in key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def fill(
    rows: Iterable[MetricRow],
    manifests: Mapping[str, Mapping[str, Any]],
    computed: Mapping[str, Any] | None = None,
) -> list[MetricRow]:
    """Attach each row's value, from its manifest or from `computed`.

    `computed` is keyed by metric name and exists for the rows the harness produces itself rather
    than reading from a manifest, the leakage audit above all. Without it those rows rendered as
    "not produced" beside a gate that had in fact run, which is the opposite of the table's purpose.
    """
    overrides = dict(computed or {})
    out: list[MetricRow] = []
    for row in rows:
        if row.metric in overrides:
            out.append(row.model_copy(update={"value": overrides[row.metric]}))
            continue
        if row.manifest is None or row.key is None:
            out.append(row)
            continue
        manifest = manifests.get(row.manifest)
        value = None if manifest is None else resolve(manifest, row.key)
        out.append(row.model_copy(update={"value": value}))
    return out


def uncovered(rows: Iterable[MetricRow], manifests: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Numeric manifest figures that no row addresses and no declared prefix excuses.

    Section 19.3's gate. Booleans count as figures: a pass mark is a published result.
    """
    addressed = {f"{r.manifest}.{r.key}" for r in rows if r.manifest and r.key}
    missing: list[str] = []
    for name, manifest in manifests.items():
        for key, value in _leaves(manifest):
            path = f"{name}.{key}"
            if not isinstance(value, int | float | bool):
                continue
            if path in addressed:
                continue
            if any(path == p or path.startswith(p + ".") for p in EXCLUDED_PREFIXES):
                continue
            missing.append(path)
    return sorted(missing)


def load_manifests(directory: Path) -> dict[str, dict[str, Any]]:
    """Read whichever manifests exist. A missing one leaves its rows showing `not produced`."""
    out: dict[str, dict[str, Any]] = {}
    for name, filename in MANIFESTS.items():
        path = directory / filename
        if path.exists():
            out[name] = json.loads(path.read_text(encoding="utf-8"))
    return out


def as_markdown(rows: Iterable[MetricRow]) -> str:
    """Render the table, grouped by layer, in the order the rows were declared."""
    lines: list[str] = []
    current: str | None = None
    for row in rows:
        if row.layer != current:
            current = row.layer
            lines.append(f"\n### {current}\n")
            lines.append("| metric | value | denominator | status | what would settle it | note |")
            lines.append("|---|---|---|---|---|---|")
        # `note` is rendered. Review found eight declared and none reaching the table, and they are
        # the load-bearing caveats: that a figure largely measures shared implementation, that a
        # count of one is unresolved and published as unresolved, that fourteen episodes on two
        # wells is not a benchmark.
        lines.append(
            f"| {row.metric} | {row.rendered} | {row.denominator} | `{row.status.value}` | "
            f"{row.settled_by or '—'} | {row.note or '—'} |"
        )
    return "\n".join(lines).strip() + "\n"
