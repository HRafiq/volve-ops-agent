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

    optional: bool = False
    """Whether a null for this row is the expected state rather than a defect.

    Exactly one thing is optional here: the currency figure and the day rate it rests on, which
    section 20.3 requires a caller to supply deliberately. Any other row rendering as "not produced"
    names a figure its run failed to write, and that reading is worth keeping unambiguous. Every
    previous occurrence of "not produced" in the published table was a defect, so a figure absent on
    purpose must not borrow the same words.
    """

    value: Any = None

    @property
    def rendered(self) -> str:
        if self.status is Status.DEFERRED:
            return "deferred"
        if self.value is None and self.optional:
            return "not requested"
        if self.value is None:
            return "not produced"
        if isinstance(self.value, bool):
            return "pass" if self.value else "FAIL"
        if isinstance(self.value, float):
            return f"{self.value:.4f}".rstrip("0").rstrip(".")
        return str(self.value)


#: The five manifests the project's scripts write, by the name rows refer to them by.
MANIFESTS: Final[dict[str, str]] = {
    "expectation": "run_manifest.json",
    "extraction": "extraction_run.json",
    "labels": "label_scoring_run.json",
    "investigation": "investigation_run.json",
    "postmortem": "postmortem_run.json",
}

#: Manifest paths excused from needing a table row. Independent review found the first version
#: excusing 87 of 131 numeric leaves, including the project's headline WAPE table, the label
#: distribution the README calls "the most important figure here", and `investigation.pass_marks`,
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
    "postmortem.protocol_version",
    "postmortem.postmortem_version",
    "postmortem.development_wells",
    "postmortem.hold_out_wells_excluded",
    "postmortem.correction_store_versions",
    "postmortem.cost_assumption",
    # The three published tables, excused as prefixes and justified rather than hidden. Every
    # aggregate over them has its own row: pattern count, hours, coverage, events, labelled events,
    # the single-well share of what the thresholds exclude, and the largest excluded pattern. What
    # these prefixes excuse is the per-row breakdown, which the harness prints verbatim from the
    # manifest and which a reader can regenerate from it. Review was right that the previous version
    # excused them silently and that the list walk never looked inside them at all; both are fixed,
    # and this exclusion is now a choice rather than an accident. It is also not a claim that each
    # per-well total has its own row, which an earlier version of this comment made and which was
    # false: the per-well table is excused here, not covered elsewhere.
    "postmortem.per_well",
    "postmortem.patterns",
    "postmortem.excluded_pattern_detail",
)


def _leaves(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Every scalar in a manifest, by dotted path, recursing into lists as well as dicts.

    Lists used to terminate the walk, so a figure inside one was neither covered nor excluded: it
    was invisible. Review found `postmortem.per_well` and `postmortem.patterns` excused by a prefix,
    and the deeper problem was that the prefix was never needed, because nothing looked inside them.
    The published per-well table and the whole register live in those two lists.
    """
    out: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.extend(_leaves(value, f"{prefix}{key}."))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            out.extend(_leaves(value, f"{prefix}{index}."))
    else:
        out.append((prefix.rstrip("."), obj))
    return out


def locate(manifest: Mapping[str, Any], key: str) -> tuple[Any, bool]:
    """Follow a dotted path, returning the value and whether the path existed.

    The second element is not decoration. A manifest may legitimately hold a null, so a function
    that signals absence by returning None cannot tell "not there" from "there and empty", and the
    caller that needs to know is the section 19.3 coverage gate.

    Keys are matched longest-first with backtracking, because a manifest key may itself contain
    dots. Every section 20.6 pass mark does: `pass_marks.20.6 the corpus is not empty`. Splitting on
    every dot resolved that to nothing, so **every** gate row in the published table rendered as
    "not produced" while the manifest recorded every gate as true, and the coverage gate certified
    the table as complete because it compared path *strings* and never asked whether they resolved.
    """

    def walk(node: Any, rest: str) -> tuple[Any, bool]:
        if not rest:
            return node, True
        if isinstance(node, Mapping):
            parts = rest.split(".")
            for taken in range(len(parts), 0, -1):
                head = ".".join(parts[:taken])
                if head in node:
                    value, found = walk(node[head], ".".join(parts[taken:]))
                    if found:
                        return value, True
            return None, False
        if isinstance(node, list):
            head, _, tail = rest.partition(".")
            if head.isdigit() and int(head) < len(node):
                return walk(node[int(head)], tail)
            return None, False
        return None, False

    return walk(manifest, key)


def resolve(manifest: Mapping[str, Any], key: str) -> Any:
    """`locate`, with absence flattened to None. For callers that cannot act on the difference."""
    value, _ = locate(manifest, key)
    return value


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


def unresolved(rows: Iterable[MetricRow], manifests: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Rows that name a manifest path which does not exist.

    The other half of section 19.3, and the half that was missing. `uncovered` asks whether every
    manifest figure has a row; this asks whether every row has a figure. Without it a row can name a
    key the manifest has never held, render as "not produced", and still be counted as covering the
    figure it claims to cover. That is how the gate rows came to be retyped in two places and drift
    apart, and how a row kept naming `hold_out_refusal_demonstrated` after the harness stopped
    writing it.
    """
    broken: list[str] = []
    for row in rows:
        if row.manifest is None or row.key is None:
            continue
        manifest = manifests.get(row.manifest)
        if manifest is None:
            broken.append(f"{row.manifest}.{row.key} (no such manifest)")
            continue
        if not locate(manifest, row.key)[1]:
            broken.append(f"{row.manifest}.{row.key}")
    return sorted(broken)


def uncovered(rows: Iterable[MetricRow], manifests: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Numeric manifest figures that no row addresses and no declared prefix excuses.

    Section 19.3's gate. Booleans count as figures: a pass mark is a published result.
    """
    # Only rows whose key actually resolves count as addressing anything. Membership of a set of
    # path strings was the first version, and it let a row covering a nonexistent key silence the
    # gate for the figure it named.
    addressed = {
        f"{r.manifest}.{r.key}"
        for r in rows
        if r.manifest and r.key and locate(manifests.get(r.manifest) or {}, r.key)[1]
    }
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
            f"{row.settled_by or '-'} | {row.note or '-'} |"
        )
    return "\n".join(lines).strip() + "\n"
