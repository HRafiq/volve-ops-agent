"""The operator console's API. Protocol section 21, and gate 7 in particular.

**Read-only outside the review log.** Every route here is a GET except the four that record a human
review, and section 21.6 mark 7 enumerates the routes from this application and asserts exactly
that. The console cannot write to the event store, the correction store or a finding; it cannot
re-run an investigation; and it has no actuation path of any kind. That is not a limitation to be
lifted later, it is the scope boundary the whole project is built on.

**It renders, it does not compute.** Section 21.1. Every figure in every response comes from a run
manifest or a per-episode artifact, carried by a `Sourced` that names where it came from. The
assembly lives in `volve_ops.console.assemble`; this module is routing and nothing else, so there
is no arithmetic in it to go wrong.

Run it with the `console` extra installed:

    uvicorn api.main:app --reload
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Final

from fastapi import Body, Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from volve_ops.console import assemble, labels
from volve_ops.console.payloads import Header, InvestigationDetail, Queue
from volve_ops.console.review import Action, ReviewLog, ReviewRecord, ReviewRefused, as_rows
from volve_ops.console.store import ArtifactMissing, RunStore

#: The prefix every review route carries, which is what gate 7 keys on. Named here so the gate and
#: the routes cannot drift: a reviewing route outside this prefix fails the mark.
REVIEW_PREFIX: Final[str] = "/api/review"

app = FastAPI(
    title="Volve operations console",
    description=(
        "Read-only investigation review over the Volve open dataset. Every figure resolves to a "
        "run manifest or a fact id. No model is called by any route."
    ),
    version="console-v0",
)

#: The store and the log as dependencies rather than module globals, so a test can point them at a
#: temporary directory. Not a nicety: the review log is append-only, so a test that wrote to the
#: real one would leave records a later run could cite and which nothing could remove. The
#: correction store's gate learned the same lesson in Phase 5.
def get_store() -> RunStore:
    return RunStore()


def get_log() -> ReviewLog:
    return ReviewLog()


StoreDep = Annotated[RunStore, Depends(get_store)]
LogDep = Annotated[ReviewLog, Depends(get_log)]


class ReviewRequest(BaseModel):
    """What a reviewer sends. The actor is required: an unattributed judgement is not a review."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor: str
    note: str | None = None


class ReviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recorded: ReviewRecord
    state: str
    disclaimer: str


def _not_found(exc: ArtifactMissing) -> HTTPException:
    """A missing artifact is a 404 with the reason, never an empty 200.

    Section 21.1's store refuses to serve a screen it has no artifact for, and this keeps that
    refusal visible to the caller. A 200 with an empty body would render as a screen that looks
    like an answer.
    """
    return HTTPException(status_code=404, detail=str(exc))


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness, and nothing else. No figure, so nothing to source."""
    return {"status": "ok", "version": app.version}


@app.get("/api/header")
def header(store: StoreDep) -> Header:
    """Decision 12's header: operational and data state first, build metadata behind a popover."""
    try:
        return assemble.header(store)
    except ArtifactMissing as exc:
        raise _not_found(exc) from exc


@app.get("/api/production/queue")
def queue(store: StoreDep) -> Queue:
    """The investigation queue, its KPI strip and the priority rule printed under it."""
    try:
        return assemble.queue(store)
    except ArtifactMissing as exc:
        raise _not_found(exc) from exc


@app.get("/api/investigations/{investigation_id}")
def investigation(investigation_id: str, store: StoreDep) -> InvestigationDetail:
    """One investigation. The signature screen of decision 4."""
    try:
        return assemble.detail(store, investigation_id)
    except ArtifactMissing as exc:
        raise _not_found(exc) from exc


@app.get("/api/investigations/{investigation_id}/facts")
def facts(investigation_id: str, store: StoreDep) -> list[dict[str, Any]]:
    """The fact ledger for one investigation, which is what an evidence drawer resolves against.

    Served whole rather than per fact, because decision 7's drawer shows a fact's lineage and a
    reader checking one by hand should be able to walk the whole ledger without guessing ids.
    """
    try:
        row = store.by_id(investigation_id)
        artifacts = store.artifacts_for(str(row["well"]), str(row["onset"]))
    except ArtifactMissing as exc:
        raise _not_found(exc) from exc
    return [dict(fact) for fact in artifacts.facts]


@app.get("/api/investigations/{investigation_id}/trace")
def trace(investigation_id: str, store: StoreDep) -> dict[str, Any]:
    """The observable workflow timeline. Decision 11, and never hidden reasoning.

    What this returns is the recorded steps: which stage ran, what it looked at, what it cost. A
    model's intermediate text is not here because no model is called, and if one ever is, section
    18.1's trace is still a record of actions rather than of thoughts.
    """
    try:
        row = store.by_id(investigation_id)
        artifacts = store.artifacts_for(str(row["well"]), str(row["onset"]))
    except ArtifactMissing as exc:
        raise _not_found(exc) from exc
    return dict(artifacts.trace)


@app.get("/api/investigations/{investigation_id}/review")
def review_history(investigation_id: str, log: LogDep) -> dict[str, Any]:
    """Every review action against one investigation, in order, with the state they imply."""
    records = log.for_investigation(investigation_id)
    return {
        "investigation_id": investigation_id,
        "state": log.state_of(investigation_id),
        "records": as_rows(records),
        "actions": dict(labels.REVIEW_ACTION),
        "disclaimer": labels.REVIEW_DISCLAIMER,
    }


def _record(
    investigation_id: str,
    action: Action,
    request: ReviewRequest,
    store: RunStore,
    log: ReviewLog,
) -> ReviewResponse:
    """The one write this API has, and every review route goes through it."""
    try:
        row = store.by_id(investigation_id)
        artifacts = store.artifacts_for(str(row["well"]), str(row["onset"]))
    except ArtifactMissing as exc:
        raise _not_found(exc) from exc
    try:
        recorded = log.append(
            investigation_id,
            action,
            actor=request.actor,
            investigator_version=str(artifacts.finding.get("investigator_version", "unknown")),
            protocol_version=str(store.manifests()["investigation"].get("protocol_version", "")),
            note=request.note,
            now=dt.datetime.now(tz=dt.UTC),
        )
    except ReviewRefused as refused:
        # 409, not 400. The request was well formed and the log's state is what refused it, which
        # is a different thing from a malformed body and the caller should be able to tell them
        # apart: one is worth retrying after a new run, the other never is.
        raise HTTPException(status_code=409, detail=str(refused)) from refused
    return ReviewResponse(
        recorded=recorded,
        state=log.state_of(investigation_id),
        disclaimer=labels.REVIEW_DISCLAIMER,
    )


@app.post(f"{REVIEW_PREFIX}/{{investigation_id}}/confirm")
def confirm(
    investigation_id: str,
    request: Annotated[ReviewRequest, Body()],
    store: StoreDep,
    log: LogDep,
) -> ReviewResponse:
    """Confirm finding. Records a judgement of the assessment, and authorises nothing."""
    return _record(investigation_id, Action.CONFIRM, request, store, log)


@app.post(f"{REVIEW_PREFIX}/{{investigation_id}}/dismiss")
def dismiss(
    investigation_id: str,
    request: Annotated[ReviewRequest, Body()],
    store: StoreDep,
    log: LogDep,
) -> ReviewResponse:
    """Dismiss. Equally final, and equally not an operational decision."""
    return _record(investigation_id, Action.DISMISS, request, store, log)


@app.post(f"{REVIEW_PREFIX}/{{investigation_id}}/request-more-evidence")
def request_more_evidence(
    investigation_id: str,
    request: Annotated[ReviewRequest, Body()],
    store: StoreDep,
    log: LogDep,
) -> ReviewResponse:
    """Request more evidence. Records the request; a new investigation run is what satisfies it.

    Deliberately not a re-run trigger. Section 21.1 keeps the console out of the business of
    producing findings, and a console that could produce one would be producing them.
    """
    return _record(investigation_id, Action.REQUEST_MORE_EVIDENCE, request, store, log)


@app.post(f"{REVIEW_PREFIX}/{{investigation_id}}/correction")
def add_correction(
    investigation_id: str,
    request: Annotated[ReviewRequest, Body()],
    store: StoreDep,
    log: LogDep,
) -> ReviewResponse:
    """Add correction. Appends a revision; the finding keeps its text."""
    return _record(investigation_id, Action.ADD_CORRECTION, request, store, log)


def route_table() -> list[tuple[str, frozenset[str]]]:
    """Every route and the methods it accepts, for section 21.6 mark 7.

    Read off the application rather than written down, so a route added without a thought about its
    methods fails the mark instead of shipping.
    """
    table: list[tuple[str, frozenset[str]]] = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if isinstance(path, str) and methods:
            table.append((path, frozenset(str(m) for m in methods)))
    return sorted(table)
