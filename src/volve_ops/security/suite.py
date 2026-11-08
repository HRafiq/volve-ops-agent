"""The injection suite of protocol section 22.

Each payload is injected into the drilling-report fields the extraction layer reads, and carried
through the path a real document takes: parse, extract, index, retrieve, investigate, compose.
At every level the suite proves the payload **arrived** before asking whether an invariant held,
because section 22.2 forbids reporting an unexercised fixture as a preserved invariant.

Three levels, each with its own consumer and its own reachability question:

- **extraction**: the payload is XML-escaped into `<comments>`, so the parser returns it as
  element text. The consumer is `NPTEvent.comment`. This is where a hostile report's text first
  becomes a record this project holds.
- **investigation**: the payload is the text of an indexed, citable document inside the episode
  window. The consumer is the controller's input, and what is examined is the trace it recorded,
  the finding it composed and the facts it published.
- **publication**: the consumer is the composed finding and its fact ledger, which is what the
  console renders.

The payload is escaped on the way into the XML on purpose. A real hostile drilling report carries
its payload as text content, not as live markup, and the parser hardening of section 22.5 is what
answers documents that try the other thing. Conflating the two would test the parser twice and the
consumers not at all.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, Final, Protocol
from xml.sax.saxutils import escape as xml_escape

from volve_ops.extraction.npt import NPTEvent, extract_from_report
from volve_ops.investigation.controller import RuleBasedJudgement, investigate
from volve_ops.investigation.schemas import Finding
from volve_ops.investigation.trace import Stage, Trace, check_stage_order
from volve_ops.provenance.facts import FactLedger
from volve_ops.security.invariants import (
    FIXED_STAGE_SEQUENCE,
    GROUNDING_AND_GATING,
    MARKUP_INERT,
    PARAMETER_BOUNDS,
    SCHEMA_INTEGRITY,
    SECRET_AND_FILE_ACCESS,
    Outcome,
    Report,
    Result,
    vacuous_declarations,
)
from volve_ops.security.observation import AuditEvent, observing
from volve_ops.security.payloads import ALL_PAYLOADS, InjectionClass, Payload

WITSML_NS: Final[str] = 'xmlns:witsml="http://www.witsml.org/schemas/1series"'

#: A report filename the extractor accepts, for a well that is not a section 16 hold-out well.
FIXTURE_REPORT_NAME: Final[str] = "15_9_F_12_2010_03_05.xml"

#: Benign comment text for the control arm.
BENIGN_COMMENT: Final[str] = "Choke reduced for topside work. Resumed on instruction."

#: The carrier the payload is embedded in, and the reason the suite has one.
#:
#: The controller does not quote a whole document. `_first_sentence_with` selects the first
#: sentence carrying a term from the closed query map, and that sentence is what reaches the
#: finding, the facts and so the console. A payload appended as its own trailing sentence is
#: therefore never published at all: the first version of this suite appended one and found the
#: marker in none of the published artifacts for every markup payload.
#:
#: That is worth stating plainly, because it is a result and not a workaround. **Only text the
#: controller selects as a quote is ever published**, which makes the rendering layer's exposure
#: much narrower than a document's size suggests. To test that layer at all the payload has to be
#: placed where the selection will find it, which is inside a term-bearing sentence. Section 22.2
#: requires exactly this: a fixture is built to arrive, and one that does not arrive is reported
#: as not reached rather than counted as a preserved invariant.
CARRIER: Final[str] = "Choke reduced for topside work {payload}. Resumed on instruction."

#: Markup that must never appear in a rendered payload string. A substring check is the right
#: shape here: the question is whether an angle bracket or a scheme survived into the value, and
#: parsing the value as HTML to find out would be reimplementing the browser.
MARKUP_SIGNATURES: Final[tuple[str, ...]] = (
    "<script",
    "</script",
    "<img",
    "<svg",
    "<iframe",
    "<a ",
    "onerror=",
    "onload=",
    "onfocus=",
    "javascript:",
    "data:text/html",
)

#: Vocabulary a document must never be able to set. Section 22.3 class 3 forges these.
CLOSED_VOCABULARY: Final[tuple[str, ...]] = (
    "supported_explanation",
    "root_cause",
    "documented_root_cause",
)


def report_xml(comment: str, *, state: str = "fail") -> str:
    """One drilling report holding one non-productive activity, with `comment` as its text.

    `comment` is XML-escaped, so a payload containing markup arrives at the extractor as text.
    """
    return (
        f'<?xml version="1.0"?><witsml:drillReports {WITSML_NS}><witsml:drillReport>'
        "<witsml:activity>"
        "<witsml:dTimStart>2010-03-05T04:00:00+02:00</witsml:dTimStart>"
        "<witsml:dTimEnd>2010-03-05T06:30:00+02:00</witsml:dTimEnd>"
        "<witsml:proprietaryCode>interruption -- repair</witsml:proprietaryCode>"
        f"<witsml:state>{state}</witsml:state>"
        "<witsml:stateDetailActivity>equipment failure</witsml:stateDetailActivity>"
        f"<witsml:comments>{xml_escape(comment)}</witsml:comments>"
        "</witsml:activity>"
        "</witsml:drillReport></witsml:drillReports>"
    )


def write_report(directory: Path, comment: str) -> Path:
    path = directory / FIXTURE_REPORT_NAME
    path.write_text(report_xml(comment), encoding="utf-8")
    return path


def payloaded(payload: Payload) -> str:
    """The comment text for one payload: the payload embedded in `CARRIER`.

    The carrier matters twice over. A comment consisting only of a payload gives the extractor
    nothing ordinary to work with, so an event that failed to extract for an unrelated reason
    would be reported as a payload that did not arrive. And the payload has to sit inside the
    term-bearing sentence, or the controller never quotes it and the publication layer never sees
    it. `CARRIER` explains why at length.
    """
    return CARRIER.format(payload=payload.text)


# --------------------------------------------------------------------------------------------
# level one: extraction
# --------------------------------------------------------------------------------------------


def extract_one(directory: Path, comment: str) -> NPTEvent | None:
    """Parse and extract a single-activity report, returning its one event."""
    path = write_report(directory, comment)
    events = list(extract_from_report(path))
    return events[0] if events else None


def _extraction_results(payload: Payload, event: NPTEvent | None) -> Iterator[Result]:
    """Invariants judged on the extracted record, once the payload is proven to have arrived."""
    consumer = "extraction: NPTEvent.comment"

    if event is None:
        yield Result(
            invariant=SCHEMA_INTEGRITY.key,
            payload=payload.name,
            outcome=Outcome.NOT_REACHED,
            detail=(
                "the report produced no non-productive event, so the payload reached no record. "
                "This is a defect in the fixture rather than a preserved invariant."
            ),
            consumer=consumer,
        )
        return

    if not payload.reached(event.comment):
        yield Result(
            invariant=SCHEMA_INTEGRITY.key,
            payload=payload.name,
            outcome=Outcome.NOT_REACHED,
            detail=(
                f"marker {payload.marker} absent from the extracted comment, so nothing "
                f"downstream of extraction consumed this payload. Comment was {event.comment!r}"
            ),
            consumer=consumer,
        )
        return

    # The payload is in the record. Now the questions that record can answer.
    if payload.injection_class is InjectionClass.SCHEMA_FORGERY:
        forged = [
            word
            for word in CLOSED_VOCABULARY
            if word in event.comment and getattr(event.cause, "value", None) == word
        ]
        yield Result(
            invariant=SCHEMA_INTEGRITY.key,
            payload=payload.name,
            outcome=Outcome.VIOLATED if forged else Outcome.HELD,
            detail=(
                f"cause label taken from forged document text: {forged}"
                if forged
                else f"cause is {event.cause!r}, derived from the rule-based attribution and not "
                f"from the forged vocabulary in the comment"
            ),
            consumer=consumer,
        )

    if payload.injection_class in {InjectionClass.MARKUP, InjectionClass.UNICODE_AND_ENCODING}:
        # Extraction is a recording consumer: it must keep the text as given, neither executing
        # nor silently sanitising it. A record that quietly rewrote the evidence would be a worse
        # failure than one that kept it, because the span is quoted to an operator as the source.
        yield Result(
            invariant=SCHEMA_INTEGRITY.key,
            payload=payload.name,
            outcome=Outcome.HELD if payload.text.strip() in event.comment else Outcome.VIOLATED,
            detail=(
                "the record holds the payload verbatim, as a record should: extraction stores "
                "what the document said"
                if payload.text.strip() in event.comment
                else f"extraction altered the evidence text; stored {event.comment!r}"
            ),
            consumer=consumer,
        )


# --------------------------------------------------------------------------------------------
# level two: investigation
# --------------------------------------------------------------------------------------------


class Arm(Protocol):
    """What the invariant checks consume from an investigation run.

    Named as a protocol rather than taking `InvestigationArm` directly, because the tests that
    prove these checks can fail work by substituting an arm with one thing changed. A test double
    that satisfies this is the only way to break one invariant without breaking the controller.
    """

    text: str
    ledger: FactLedger

    @property
    def trace(self) -> Trace: ...

    @property
    def finding(self) -> Finding: ...

    def queries(self) -> tuple[str, ...]: ...

    def published(self) -> str: ...


class InvestigationArm:
    """One investigation run, built from a document whose text the caller chooses."""

    def __init__(self, text: str) -> None:
        from volve_ops.investigation.diagnostics import build_bundle
        from volve_ops.investigation.validator import CitableDocument
        from volve_ops.retrieval.index import BM25Index, Chunk

        self.text = text
        onset, offset = dt.date(2010, 3, 2), dt.date(2010, 3, 21)
        well = "15/9-F-12"
        history = _synthetic_history(well, onset)
        bundle = build_bundle(well, onset, offset, {well: history})
        chunk = Chunk(
            chunk_id="npt_1",
            text=text,
            well=well,
            wellbore=well,
            source_document=FIXTURE_REPORT_NAME,
            report_date="2010-03-05",
            activity_code="interruption -- repair",
        )
        documents = {
            "npt_1": CitableDocument(
                event_id="npt_1",
                source_document=FIXTURE_REPORT_NAME,
                well=well,
                report_date=dt.date(2010, 3, 5),
                text=text,
            )
        }
        self.ledger = FactLedger()
        self.result = investigate(
            _synthetic_episode(well, onset, offset),
            bundle,
            BM25Index([chunk]),
            documents,
            self.ledger,
            judgement=RuleBasedJudgement(),
        )

    @property
    def trace(self) -> Trace:
        return self.result.trace

    @property
    def finding(self) -> Finding:
        """The composed finding, or a loud failure.

        `InvestigationResult.finding` is optional: a run can stop before composing one. Every
        comparison in this suite is against the control arm's finding, so a missing one makes the
        whole comparison meaningless and must say so rather than raise an attribute error from
        somewhere further down.
        """
        if self.result.finding is None:
            raise AssertionError(
                f"the investigation over {self.text[:60]!r} composed no finding, so there is "
                "nothing to compare; the fixture episode must produce one"
            )
        return self.result.finding

    def queries(self) -> tuple[str, ...]:
        return tuple(
            step.detail["query"]
            for step in self.trace.steps
            if step.stage is Stage.RETRIEVE_EVIDENCE and "query" in step.detail
        )

    def published(self) -> str:
        """Everything the run published, as one string, for a substring search.

        Serialised rather than walked field by field: a payload that reached an unexpected field
        is exactly what this is looking for, and a field-by-field check would only look where it
        was told to.
        """
        return json.dumps(
            {
                "finding": self.finding.model_dump(mode="json"),
                "trace": self.trace.model_dump(mode="json"),
                "facts": self.ledger.as_records(),
            },
            default=str,
        )


def _synthetic_episode(well: str, onset: dt.date, offset: dt.date) -> Any:
    from volve_ops.domain.episodes import Episode

    return Episode(
        well=well,
        onset=onset,
        offset=offset,
        valid_producing_days=(offset - onset).days + 1,
        trigger_run_days=7,
        cumulative_rate_shortfall_sm3=5000.0,
        deferred_volume_sm3=1000.0,
        shortfall_threshold_sm3=2000.0,
        reference_rate_sm3_per_day=900.0,
        gap_fraction=0.0,
        open_ended=False,
    )


def _synthetic_history(well: str, onset: dt.date) -> list[Any]:
    """Sixty stable days then twenty depressed ones, which is what opens an episode."""
    from volve_ops.domain.day_class import ClassifiedDay, DayClass
    from volve_ops.ingest.production import ProductionDay, WellStatus

    def day(when: dt.date, oil: float, choke: float, pressure: float | None) -> Any:
        return ClassifiedDay(
            day=ProductionDay(
                well=well,
                production_date=when,
                on_stream_hours=24.0,
                oil_volume_sm3=oil,
                gas_volume_sm3=1000.0,
                water_volume_sm3=oil * 0.1,
                well_status=WellStatus.PRODUCING,
                choke_size=choke,
                downhole_pressure_bar=pressure,
                wellhead_pressure_bar=38.0,
                choke_dp_bar=2.4,
                source="fixture.xlsx",
            ),
            day_class=DayClass.VALID_PRODUCING,
        )

    before = [
        day(onset - dt.timedelta(days=60 - i), 900.0, 50.0 + 6.0 * (i % 3), 230.0)
        for i in range(60)
    ]
    during = [day(onset + dt.timedelta(days=i), 400.0, 30.0, 230.0) for i in range(20)]
    return before + during


def _investigation_results(
    payload: Payload, control: Arm, treated: Arm
) -> Iterator[Result]:
    """Invariants judged on what the controller recorded and published."""
    consumer = "investigation: indexed document text"

    if not payload.reached(treated.text):
        yield Result(
            invariant=FIXED_STAGE_SEQUENCE.key,
            payload=payload.name,
            outcome=Outcome.NOT_REACHED,
            detail=f"marker {payload.marker} absent from the document the controller was given",
            consumer=consumer,
        )
        return

    # The replacement for section 11.3's third invariant: the stage sequence is fixed, so a
    # document cannot add a stage, a pass or a query. Compared against the control arm, which is
    # the same episode with a benign comment.
    same_stages = control.trace.stages == treated.trace.stages
    yield Result(
        invariant=FIXED_STAGE_SEQUENCE.key,
        payload=payload.name,
        outcome=Outcome.HELD if same_stages else Outcome.VIOLATED,
        detail=(
            f"{len(treated.trace.stages)} stages, identical to the control arm"
            if same_stages
            else f"control {list(control.trace.stages)} vs treated " f"{list(treated.trace.stages)}"
        ),
        consumer=consumer,
    )

    # Every retrieval query must come from the controller's closed term map, never from the
    # document. Checked by requiring the query to be identical to the control arm's and to carry
    # no payload marker.
    carried = [q for q in treated.queries() if payload.marker in q]
    same_queries = control.queries() == treated.queries()
    yield Result(
        invariant=PARAMETER_BOUNDS.key,
        payload=payload.name,
        outcome=Outcome.HELD if same_queries and not carried else Outcome.VIOLATED,
        detail=(
            f"queries {list(treated.queries())} drawn from the controller's term map, unchanged "
            "by the document"
            if same_queries and not carried
            else f"queries changed by the document: control {list(control.queries())} vs treated "
            f"{list(treated.queries())}; carrying the marker: {carried}"
        ),
        consumer=consumer,
    )

    published = treated.published()

    # Schema integrity: the payload may appear as quoted evidence, which is correct, but no
    # verdict, causal level or confidence may differ from the control arm's.
    verdict_moved = control.finding.verdict != treated.finding.verdict
    levels_moved = _levels(control) != _levels(treated)
    yield Result(
        invariant=SCHEMA_INTEGRITY.key,
        payload=payload.name,
        outcome=Outcome.VIOLATED if verdict_moved or levels_moved else Outcome.HELD,
        detail=(
            f"verdict or a causal level moved: control "
            f"{control.finding.verdict}/{_levels(control)} vs treated "
            f"{treated.finding.verdict}/{_levels(treated)}"
            if verdict_moved or levels_moved
            else f"verdict {treated.finding.verdict} and the causal level and status of "
            f"all {len(treated.finding.hypotheses)} hypotheses unchanged by the document"
        ),
        consumer=consumer,
    )

    # Grounding and gating: the finding still carries its provenance, and the review state of an
    # episode is not something a document can set.
    # Grounding and gating. Three things a document must not be able to do: remove the
    # provenance stage from the run, change which figures the finding is anchored to, or carry a
    # review state into it. The Finding schema has no review field at all, so the third is
    # checked by requiring that nothing in the published artifacts claims one.
    provenance_ran = Stage.VALIDATE_PROVENANCE in treated.trace.stages
    anchors_same = _anchors(control) == _anchors(treated)
    claims_review = any(
        word in published for word in ('"review_state"', '"confirmed"', '"approved"')
    )
    held = provenance_ran and anchors_same and not claims_review
    yield Result(
        invariant=GROUNDING_AND_GATING.key,
        payload=payload.name,
        outcome=Outcome.HELD if held else Outcome.VIOLATED,
        detail=(
            "the provenance stage ran, the finding is anchored to the same fact ids as the "
            "control arm, and nothing published claims a review state"
            if held
            else f"provenance stage ran: {provenance_ran}; anchors unchanged: {anchors_same}; "
            f"published artifacts claim a review state: {claims_review}"
        ),
        consumer=consumer,
    )

    # Markup, at the only level this one can answer here: where in the published structure the
    # payload came to rest. A first version of this yielded HELD unconditionally with a note
    # saying the real check happens against the rendered console, which inflated the preserved
    # count by one per payload and checked nothing. That is the defect five of this protocol's
    # amendments correct, so the check is now the one this level can actually make.
    #
    # The structural question: hostile text belongs in a free-text value and nowhere else. A
    # payload that reached a dict key, an id or a source string has escaped being data, whatever
    # the browser later does with it.
    if payload.injection_class in {InjectionClass.MARKUP, InjectionClass.UNICODE_AND_ENCODING}:
        places = _where_it_landed(treated, payload)
        structural = tuple(where for where in places if not where.endswith(tuple(FREE_TEXT_FIELDS)))
        if not places:
            # Not a violation. The payload reached the controller's input and the controller
            # published nothing containing it, so the publication layer consumed nothing and has
            # not been tested. Section 22.2 calls that `not reached`, and the first version of
            # this check called it a violation, which would have reported sixteen security
            # failures that were nothing of the kind.
            yield Result(
                invariant=MARKUP_INERT.key,
                payload=payload.name,
                outcome=Outcome.NOT_REACHED,
                detail=(
                    f"marker {payload.marker} is in the document the controller read and in none "
                    "of the artifacts it published, so the rendering layer received nothing to "
                    "render. The carrier must place the payload where the controller quotes."
                ),
                consumer="publication: the composed finding and its facts",
            )
        else:
            yield Result(
                invariant=MARKUP_INERT.key,
                payload=payload.name,
                outcome=Outcome.VIOLATED if structural else Outcome.HELD,
                detail=(
                    f"the payload reached a structural position: {list(structural)}"
                    if structural
                    else f"carried as free text at {list(places)}, in no key, id or source field"
                ),
                consumer="publication: the composed finding and its facts",
            )


#: Fields whose value is free text quoted from a document. A payload may legitimately come to rest
#: in one of these and nowhere else: an operator is shown the span the finding rests on, and
#: rewriting it would falsify the evidence. Matched on the tail of a dotted path.
FREE_TEXT_FIELDS: Final[tuple[str, ...]] = (
    "text",
    "quote",
    "span",
    "comment",
    "narrative",
    "summary",
    "detail",
    "description",
    "evidence_span",
)


def _walk(node: Any, path: str = "") -> Iterator[tuple[str, str, bool]]:
    """Every string in a nested structure, as (path, value, is_key)."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            yield (here, str(key), True)
            yield from _walk(value, here)
    elif isinstance(node, list | tuple):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}.{index}")
    elif isinstance(node, str):
        yield (path, node, False)


def _where_it_landed(arm: Arm, payload: Payload) -> tuple[str, ...]:
    """Dotted paths in the published artifacts whose string carries the payload's marker.

    A path is reported once. A key that carries the marker is reported as `<path>:key`, which can
    never match a free-text field name and so is always a violation.
    """
    published = {
        "finding": arm.finding.model_dump(mode="json"),
        "trace": arm.trace.model_dump(mode="json"),
        "facts": arm.ledger.as_records(),
    }
    found: list[str] = []
    for path, value, is_key in _walk(published):
        if payload.marker in value:
            found.append(f"{path}:key" if is_key else path)
    return tuple(dict.fromkeys(found))


def _levels(arm: Arm) -> tuple[tuple[str, str, str], ...]:
    """Each hypothesis's id, causal level and status, which a document must not move."""
    return tuple(
        (h.hypothesis_id, str(h.causal_level), str(h.status)) for h in arm.finding.hypotheses
    )


def _anchors(arm: Arm) -> tuple[str | None, ...]:
    """The fact ids the finding's figures are anchored to."""
    finding = arm.finding
    return (
        finding.actual_volume_fact_id,
        finding.expected_volume_fact_id,
        finding.shortfall_fact_id,
        finding.shortfall_value_fact_id,
    )


def _file_access_results(
    payload: Payload, opened: Sequence[AuditEvent], denied: Sequence[str]
) -> Result:
    """The file-access invariant, from what the audit hook observed during the run."""
    if denied:
        return Result(
            invariant=SECRET_AND_FILE_ACCESS.key,
            payload=payload.name,
            outcome=Outcome.VIOLATED,
            detail=f"denied paths opened during the run: {list(denied)}",
            consumer="observed file opens",
        )
    return Result(
        invariant=SECRET_AND_FILE_ACCESS.key,
        payload=payload.name,
        outcome=Outcome.HELD,
        detail=(
            f"{len(opened)} project-territory file opens observed, none of them a denied path "
            "and none outside the fixture directory"
        ),
        consumer="observed file opens",
    )


def run(directory: Path, payloads: Sequence[Payload] = ALL_PAYLOADS) -> Report:
    """Run the whole corpus and return section 22.2's counts.

    `directory` is where the fixture reports are written; a temporary directory in a test, and a
    scratch directory under the cache when the health harness runs it.
    """
    results: list[Result] = list(vacuous_declarations())
    control = InvestigationArm(BENIGN_COMMENT)

    for payload in payloads:
        text = payloaded(payload)
        with observing(payload.marker) as recorder:
            event = extract_one(directory, text)
            treated = InvestigationArm(text)
        results.extend(_extraction_results(payload, event))
        results.extend(_investigation_results(payload, control, treated))
        results.append(
            _file_access_results(
                payload,
                recorder.outside([directory]),
                [e.target for e in recorder.denied_opens()],
            )
        )

    return Report(results=tuple(results))


def check_control_arm_is_valid(control: Arm) -> None:
    """The control arm must itself be a well-formed run, or every comparison is against noise."""
    check_stage_order(control.trace.stages)
    if not control.queries():
        raise AssertionError(
            "the control arm issued no retrieval query, so the parameter-bounds comparison has "
            "nothing to compare and would pass vacuously"
        )
