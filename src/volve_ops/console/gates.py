"""Protocol section 21.6's eight pass marks, as functions rather than expressions in a script.

Five phases of this project have ended with a gate that could not fail, and the diagnosis has not
changed: the gate was written in the same file as the thing it checked, in the same sitting, and no
failing case was ever executed. So every mark here is a function with a test that makes it fail, and
every one reports **what it examined**, because a gate that passed over an empty set has
demonstrated nothing.

Two of the eight are structural rather than inspectional, and that is deliberate. Mark 1 is mostly
enforced by the payload types, where an unsourced figure cannot be constructed; the gate's remaining
job is to confirm no bare number slipped into a plain container and that every source resolves. Mark
5 is enforced by `Money`, which refuses an amount without its assumption at construction. A gate
that is the last line rather than the only line is the one lesson worth carrying out of Phase 5.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from volve_ops.console import labels, priority
from volve_ops.console.payloads import EvidenceCoverage, Money
from volve_ops.console.review import Action, ReviewLog, ReviewRefused
from volve_ops.console.sources import (
    Sourced,
    SourcedTable,
    resolve_source,
    sources_in,
    tables_in,
    unsourced_figures,
)
from volve_ops.extraction.sampling import HOLD_OUT_WELLS

#: How a mockup placeholder is recognised, section 21.2.
#:
#: The **rule** is here and the **figures** are not, because the mockup lives in a local-only folder
#: and copying its contents into a tracked file would publish private material to make a test
#: convenient. Protocol amendment 11 records the change, and section 21.2 now says what this mark
#: does: it said the figures would be enumerated in the test suite, and they are extracted from the
#: mockup at check time instead.
#:
#: What survives a fresh clone without the mockup is mark 1, which makes an invented figure
#: unconstructible rather than merely detectable. This mark is the belt to that braces, and it
#: reports `examined=0` when the mockup is absent so nobody mistakes a skipped check for a passed
#: one.
PLACEHOLDER_SHAPES: Final[dict[str, str]] = {
    "thousands-separated figure": r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b",
    "fact or evidence id": r"\b(?:fact|doc_ev|derived)_[0-9a-zA-Z]+\b",
    "version name": r"\b(?:exp|prompt|idx|corr)-v\d+\b",
    "commit-like hash": r"\b[0-9a-f]{7,}\b",
    "percentage pass mark": r"\d+(?:\.\d+)?\s*%",
    "currency figure": r"(?:USD|\$)\s?\d[\d,.]*",
}


class GateOutcome(BaseModel):
    """One pass mark: whether it held, what it looked at, and what went wrong."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    passed: bool
    examined: int
    detail: tuple[str, ...] = ()

    @property
    def vacuous(self) -> bool:
        return self.passed and self.examined == 0


GATE_NAMES: Final[tuple[str, ...]] = (
    "21.6 every payload figure resolves to a source",
    "21.2 no mockup placeholder appears",
    "21.6 no hold-out well in any payload",
    "21.4 abstention renders as its own state",
    "21.6 every money figure carries its assumption",
    "21.6 the review log is append-only",
    "21.6 the API is read-only outside the review log",
    "21.5 the priority score equals the rule as printed",
)


def figures_resolve(
    payloads: Mapping[str, Any],
    manifests: Mapping[str, Mapping[str, Any]],
    *,
    fact_ids: frozenset[str],
    artifacts: Path,
) -> GateOutcome:
    """Mark 1. Every numeric leaf is sourced, every source resolves, every table counts its rows."""
    problems: list[str] = []
    examined = 0
    for name, payload in payloads.items():
        for path in unsourced_figures(payload):
            problems.append(f"{name}: {path} is a bare number with no source")
        for source in sources_in(payload):
            examined += 1
            if not resolve_source(source, manifests, fact_ids=fact_ids, artifacts=artifacts):
                problems.append(f"{name}: {source!r} resolves to nothing")
        for table in tables_in(payload):
            examined += 1
            mismatch = table.rows_mismatch()
            if mismatch:
                problems.append(
                    f"{name}: a table {mismatch}; the row count is what bounds amendment 10's "
                    "exemption, so this voids it"
                )
            # Amendment 10's third bound, which nothing checked until review found it violated by
            # the exemption's only user. A derived column is permitted and must be declared, so a
            # result cannot ride into a table unnoticed beside the records.
            undeclared = _undeclared_results(table)
            if undeclared:
                problems.append(
                    f"{name}: a table carries undeclared derived columns {sorted(undeclared)}; "
                    "amendment 11 requires a result in a table to be declared in `derived_columns`"
                )
    return GateOutcome(
        name=GATE_NAMES[0],
        passed=not problems,
        examined=examined,
        detail=tuple(problems[:6]),
    )


#: Column names that name a computed quantity rather than a reading. Deliberately a small, literal
#: list: the alternative is a heuristic over names, and a heuristic that decides what counts as a
#: result is exactly the kind of judgement a gate should not be making on its own.
RESULT_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "expected",
        "lower",
        "upper",
        "below_band",
        "shortfall",
        "cumulative_shortfall",
        "deferred_volume",
        "score",
        "priority_score",
        "share",
        "fraction",
        "rate_change",
        "standardised_shift",
    }
)


def _undeclared_results(table: SourcedTable) -> set[str]:
    """Result-shaped columns a table carries without declaring them."""
    rows = getattr(table, table.rows_field, None)
    if not isinstance(rows, tuple | list) or not rows:
        return set()
    first = rows[0]
    names = (
        {name for name, _ in first} if isinstance(first, BaseModel) else set(getattr(first, "", []))
    )
    return (names & RESULT_COLUMNS) - set(table.derived_columns)


def no_placeholder_appears(rendered: Mapping[str, str], mockup: Path) -> GateOutcome:
    """Mark 2, section 21.2. Figures extracted from the mockup at check time, never stored here."""
    if not mockup.exists():
        return GateOutcome(
            name=GATE_NAMES[1],
            passed=True,
            examined=0,
            detail=(
                f"{mockup} is not present, so nothing was compared. Mark 1 is what stands in a "
                "clone without it: an invented figure cannot be constructed, only detected here.",
            ),
        )
    text = mockup.read_text(encoding="utf-8")
    forbidden: dict[str, str] = {}
    for kind, pattern in PLACEHOLDER_SHAPES.items():
        for hit in set(re.findall(pattern, text)):
            forbidden[hit] = kind
    problems: list[str] = []
    for name, body in rendered.items():
        for hit, kind in forbidden.items():
            if hit in body:
                problems.append(f"{name} carries {hit!r}, a {kind} from the design mockup")
    return GateOutcome(
        name=GATE_NAMES[1],
        passed=not problems,
        examined=len(forbidden),
        detail=tuple(sorted(problems)[:6]),
    )


def no_hold_out_well(rendered: Mapping[str, str]) -> GateOutcome:
    """Mark 3, section 16. Checked on what the API serves, not on the filter that built it.

    Both spellings, because the console writes a well name in prose as well as in a field, and the
    bare form is how one reaches a sentence: `15/9-F-4` and `F-4`.
    """
    problems: list[str] = []
    examined = 0
    for name, body in rendered.items():
        examined += 1
        for well in sorted(HOLD_OUT_WELLS):
            bare = well.split("-", 1)[1]
            if well in body:
                problems.append(f"{name} names {well}, held out under section 16")
            elif re.search(rf"\b{re.escape(bare)}\b", body):
                problems.append(f"{name} names {bare}, the bare form of hold-out well {well}")
    return GateOutcome(
        name=GATE_NAMES[2],
        passed=not problems,
        examined=examined,
        detail=tuple(sorted(set(problems))[:6]),
    )


def abstention_renders(coverages: Sequence[tuple[str, str, EvidenceCoverage]]) -> GateOutcome:
    """Mark 4, section 21.4.

    An abstention screen is the one most likely to degrade into a blank: there is no conclusion to
    render, so a careless implementation shows an empty card. The mark asks for the opposite, that
    both lists are populated, and it examines only the findings that actually abstained, so it
    cannot pass by looking at a supported one.
    """
    problems: list[str] = []
    examined = 0
    for investigation_id, verdict, coverage in coverages:
        if verdict != "insufficient_evidence":
            continue
        examined += 1
        if not coverage.available:
            problems.append(f"{investigation_id}: nothing listed as available")
        if not coverage.missing:
            problems.append(
                f"{investigation_id}: nothing listed as missing, which for an abstention is the "
                "screen saying there was no reason it could not conclude"
            )
        for line in coverage.missing:
            if not line.strip():
                problems.append(f"{investigation_id}: a blank line in the missing list")
    return GateOutcome(
        name=GATE_NAMES[3],
        passed=not problems,
        examined=examined,
        detail=tuple(problems[:6]),
    )


def money_carries_its_assumption(tiles: Sequence[tuple[str, Money]]) -> GateOutcome:
    """Mark 5, section 20.3 applied to a display.

    `Money` refuses an amount without an assumption at construction, so this gate exists to catch
    the case the type cannot: a tile built before the rule was added, or a dict that bypassed the
    model. It also refuses a non-finite amount, which section 20.3's post-mortem counterpart learned
    to check after review fed it `nan`.
    """
    problems: list[str] = []
    examined = 0
    for label, tile in tiles:
        examined += 1
        amount = tile.amount
        if amount is None or amount.value is None:
            if not tile.reason:
                problems.append(f"{label}: no figure and no reason, which reads as a bug")
            continue
        if not tile.assumption:
            problems.append(f"{label}: a currency figure with no assumption beside it")
        value = float(amount.value)
        if value != value or value in {float("inf"), float("-inf")}:
            problems.append(f"{label}: a non-finite currency figure")
        elif value < 0:
            problems.append(f"{label}: a negative currency figure")
    return GateOutcome(
        name=GATE_NAMES[4],
        passed=not problems,
        examined=examined,
        detail=tuple(problems[:6]),
    )


def review_log_is_append_only(log: ReviewLog) -> GateOutcome:
    """Mark 6, probed rather than asserted. Four attempts that must each be refused.

    Probed on a throwaway log and never on the real one, for the reason section 20.5 gives about the
    correction store: a record left behind by a gate is a record a later run could cite, and an
    append-only log cannot remove it.
    """
    problems: list[str] = []
    probe = "probe-never-reviewed"
    common = {
        "actor": "section 21.6 probe",
        "investigator_version": "investigator-v0",
        "protocol_version": "probe",
    }
    try:
        log.append(probe, Action.CONFIRM, **common)  # type: ignore[arg-type]
    except ReviewRefused as refused:
        return GateOutcome(
            name=GATE_NAMES[5],
            passed=False,
            examined=1,
            detail=(f"a first confirmation was refused ({refused}); the log accepts nothing",),
        )
    for action in (Action.CONFIRM, Action.DISMISS, Action.ADD_CORRECTION):
        try:
            log.append(probe, action, note="probe", **common)  # type: ignore[arg-type]
            problems.append(f"{action.value} was accepted against a settled finding")
        except ReviewRefused:
            pass
    try:
        log.append("probe-empty-correction", Action.ADD_CORRECTION, **common)  # type: ignore[arg-type]
        problems.append("a correction with no note was accepted")
    except ReviewRefused:
        pass
    if log.state_of(probe) != "confirmed":
        problems.append(f"the log reports {log.state_of(probe)!r} after a confirmation")
    return GateOutcome(
        name=GATE_NAMES[5],
        passed=not problems,
        examined=5,
        detail=tuple(problems),
    )


def api_is_read_only(routes: Sequence[tuple[str, frozenset[str]]]) -> GateOutcome:
    """Mark 7. Every route enumerated, and only a review route may accept anything but GET.

    The list comes from the application rather than from a document, so a route added without a
    thought about its methods fails here instead of shipping.
    """
    problems: list[str] = []
    allowed = {"GET", "HEAD", "OPTIONS"}
    for path, methods in routes:
        writing = {m.upper() for m in methods} - allowed
        if writing and "/review" not in path:
            problems.append(f"{path} accepts {sorted(writing)} and is not a review route")
    return GateOutcome(
        name=GATE_NAMES[6],
        passed=not problems,
        examined=len(routes),
        detail=tuple(problems),
    )


def priority_matches_the_printed_rule(
    rows: Sequence[tuple[str, int, float, int, str, str, str]],
    statement: Sequence[str],
) -> GateOutcome:
    """Mark 8. Every row recomputed from the rule as printed, not from the implementation.

    The recomputation below is written out longhand on purpose. Calling `score_episode` would ask
    the implementation whether it agrees with itself, which is the shape of four of the six defects
    Phase 5 ended with.
    """
    problems: list[str] = []
    for investigation_id, score, shortfall, days, verdict, band, review_state in rows:
        points = 3 if shortfall >= 30_000 else 2 if shortfall >= 10_000 else 1
        extra = 0
        if days >= 40:
            extra += 1
        if review_state in {"awaiting_review", "rerun_requested"}:
            extra += 1
        if verdict != "supported_explanation" and band in {"high", "moderate"}:
            extra += 1
        if points + extra != score:
            problems.append(
                f"{investigation_id}: the rule gives {points + extra} and the payload says {score}"
            )
    thresholds = (
        f"{priority.LARGE_SHORTFALL_SM3:,.0f}",
        f"{priority.MODERATE_SHORTFALL_SM3:,.0f}",
        str(priority.LONG_EPISODE_DAYS),
        str(priority.HIGH_SCORE),
    )
    printed = " ".join(statement)
    for threshold in thresholds:
        if threshold not in printed:
            problems.append(f"the printed rule does not state the threshold {threshold}")
    return GateOutcome(
        name=GATE_NAMES[7],
        passed=not problems,
        examined=len(rows),
        detail=tuple(problems[:6]),
    )


def operator_screens_avoid_engineering_words(rendered: Mapping[str, str]) -> list[str]:
    """Not a gate, a report. The console design's decision 5, measured rather than asserted.

    Returned as a list rather than a `GateOutcome` because section 21.6 does not gate on it and
    inventing a ninth mark after the fact is the move amendment 7 was written about. The harness
    prints it, and if it ever needs to gate, that is an amendment.
    """
    found: list[str] = []
    for name, body in rendered.items():
        for word in labels.engineering_words_in(body):
            found.append(f"{name}: {word!r}")
    return sorted(set(found))


def run_all(checks: Sequence[Callable[[], GateOutcome]]) -> list[GateOutcome]:
    return [check() for check in checks]


def _sourced_values(payload: Any) -> list[Sourced]:
    """Every `Sourced` in a payload. Used by the harness's own reporting, not by a gate."""
    out: list[Sourced] = []
    if isinstance(payload, Sourced):
        return [payload]
    if isinstance(payload, BaseModel):
        for _, value in payload:
            out.extend(_sourced_values(value))
        return out
    if isinstance(payload, Mapping):
        for value in payload.values():
            out.extend(_sourced_values(value))
        return out
    if isinstance(payload, str):
        return out
    if isinstance(payload, Sequence):
        for value in payload:
            out.extend(_sourced_values(value))
        return out
    return out
