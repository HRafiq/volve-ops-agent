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
from pathlib import Path
from typing import Annotated, Any, Final

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from volve_ops.console import assemble, labels, limits, rate_limit
from volve_ops.console.payloads import Header, InvestigationDetail, Queue, SystemHealth
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
    """What a reviewer sends. The actor is required: an unattributed judgement is not a review.

    Both fields are length-bounded, which protocol section 22.4 mark 6 requires and section 22.8
    fixes the numbers for. The review log is append-only, so an unbounded note is unbounded
    permanently: no route removes one. A value over the bound is refused with the limit in the
    error rather than truncated, because a silently shortened correction is a falsified record.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor: Annotated[str, Field(max_length=limits.MAX_ACTOR_CHARS)]
    note: Annotated[str | None, Field(max_length=limits.MAX_NOTE_CHARS)] = None


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


@app.middleware("http")
async def bound_requests(request: Request, call_next: Any) -> Response:
    """Section 22.8's per-client request bound, and mark 10.

    Applied to every route including the static console, with a higher bound for assets because
    one page load fetches several files. The refusal is a 429 carrying the limit and a Retry-After,
    so a caller can tell a bound from a fault.

    The limiter's own limits are in its module docstring and they are real: one process, keyed by
    peer address, fixed window. This stops a loop; it is not traffic shaping.
    """
    # Not `request.client.host` on its own. uvicorn's proxy-headers middleware runs outside this
    # one and may already have replaced the peer with a value from the caller's own header, which
    # made the bound bypassable by rotating it. `client_key` collapses an address it cannot vouch
    # for into a single shared bucket.
    client = rate_limit.client_key(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
    )
    limiter = rate_limit.limiter_for(request.url.path)
    allowed, remaining = limiter.check(client)
    if not allowed:
        retry = limiter.retry_after()
        return JSONResponse(
            status_code=429,
            content={
                "detail": (
                    f"rate limit of {limiter.limit} requests per "
                    f"{limiter.window_seconds} seconds exceeded"
                ),
                "limit": limiter.limit,
                "window_seconds": limiter.window_seconds,
            },
            headers={"Retry-After": str(retry)},
        )
    response: Response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limiter.limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response


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


@app.get("/api/system/health")
def system_health(store: StoreDep) -> SystemHealth:
    """Tab 4. Section 22 and section 21.1: it renders what the harnesses measured.

    Every figure comes from `security_run.json` or `ablation_run.json`. Nothing on this screen is
    computed here, deltas included: mark 12 requires a comparison that cannot be computed to say
    so rather than publish a zero against a baseline that does not exist.
    """
    try:
        return assemble.system_health(store)
    except ArtifactMissing as exc:
        raise _not_found(exc) from exc


@app.get("/api/production/queue")
def queue(store: StoreDep, log: LogDep) -> Queue:
    """The investigation queue, its KPI strip and the priority rule printed under it.

    The log is a dependency here because the queue reads it: a review recorded through this API
    has to reach the queue's review column, its "awaiting review" tile and the priority rule's
    review term. The first version took no log and asserted on every request that none existed.
    """
    try:
        return assemble.queue(store, log)
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
def review_history(investigation_id: str, store: StoreDep, log: LogDep) -> dict[str, Any]:
    """Every review action against one investigation, in order, with the state they imply.

    The id is resolved against the published rows before anything is read, as every other route
    that takes one does. This route did not, and it was the only one: it consulted the log alone,
    so any string at all came back 200 with a state of `awaiting_review` and the string echoed as
    an investigation id. An episode that does not exist got a confident review panel, which is the
    failure `RunStore._read` names in its own message: an empty screen looks like an answer.

    Found by a test that enumerated every route taking an id rather than checking the obvious
    ones. Nothing here opened a path built from the id, so it was never a traversal; it was a
    screen answering a question about something that is not there.
    """
    try:
        store.by_id(investigation_id)
    except ArtifactMissing as exc:
        raise _not_found(exc) from exc
    records = log.for_investigation(investigation_id)
    state = log.state_of(investigation_id)
    return {
        "investigation_id": investigation_id,
        "state": state,
        # The label beside the raw state, because the panel renders one of them to an operator and
        # printed the raw one until a pass through the running console found "state:
        # awaiting_review" under a heading that says Human review.
        "state_label": labels.review_state_label(state),
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


#: The built console, served by the same process that serves the API.
#:
#: One process rather than a dev server and a proxy, because the console is a read-only view of
#: these payloads and splitting it across two origins buys nothing but a CORS policy. `StaticFiles`
#: answers GET and HEAD only, so section 21.6 mark 7 still holds with the mount in place: the route
#: table below picks it up and the gate checks it like any other route.
_BUILT = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _BUILT.is_dir():
    app.mount("/", StaticFiles(directory=_BUILT, html=True), name="console")


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
