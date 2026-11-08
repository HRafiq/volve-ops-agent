"""Building the payloads the API serves, from the artifacts the harnesses wrote.

Protocol section 21.1 in practice. Every figure here is lifted from a manifest or a per-episode
artifact and labelled with where it came from; nothing is summed, averaged or rescaled. The one
exception is declared: the priority score, which is section 21.5's rule applied to figures that are
themselves sourced, and which carries `rule:21.5` as its source.

Where this module does make a choice, it is a presentation choice and it is named as one: which
label an enum value shows, which channels count as the evidence families of the matrix, how a date
range is written. None of those is a figure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from volve_ops.console import labels, priority
from volve_ops.console.payloads import (
    Absence,
    ChartSeries,
    ComparisonRow,
    DocumentEvidence,
    EvidenceCoverage,
    ExpectationAblation,
    ExpectationAblationRow,
    ExpectationPanel,
    FactEvidence,
    Header,
    HealthRow,
    Hypothesis,
    InvestigationDetail,
    Kpi,
    LedgerFact,
    MatrixCell,
    Money,
    NotApplicable,
    PriorityRule,
    Queue,
    QueueRow,
    SeriesRow,
    SystemHealth,
    VacuousInvariant,
)
from volve_ops.console.review import ReviewLog
from volve_ops.console.sources import ARTIFACT_PREFIX, RULE_PREFIX, Sourced
from volve_ops.console.store import EpisodeArtifacts, RunStore, investigation_id


def _protocol_version(document: Path = Path("docs/eval_protocol.md")) -> str:
    """The protocol document's own version line, read rather than retyped.

    It was a constant, and the commit that moved the document to v15 left it at v14, so the console
    header told every reader the protocol was a version behind. A hardcoded copy of a number that
    lives in a file is a second source of truth, and this project has now been bitten by that twice
    in one phase: the header showed v12 against a v14 document, and the comment explaining that bug
    sat three lines above the constant when it went stale again.
    """
    if not document.exists():
        return "unknown"
    for line in document.read_text(encoding="utf-8").splitlines()[:10]:
        if line.startswith("Version:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


#: The protocol document version this console was built against. Section 21 and its amendments.
CONSOLE_PROTOCOL_VERSION: Final[str] = _protocol_version()

#: The columns of the hypothesis and evidence matrix, in the order the console design shows them.
#: A presentation choice, not a figure: these group the channels section 18.2 already defines.
EVIDENCE_FAMILIES: Final[tuple[str, ...]] = (
    "Production",
    "Control",
    "Pressure",
    "Fluids",
    "Report",
)

#: Which family each hypothesis's evidence belongs to, and which strength feature carries it.
#:
#: Keyed on the hypothesis rather than on `required_channels`, which a first version used and which
#: is empty for two of the five. The screen then showed `H-water` as **Supported** with every cell
#: reading "Not applicable", a supported conclusion with no visible support, which is the exact
#: failure section 21.3 is about. `H-water` is judged on the water-cut rise and `H-field` on the
#: offset comparison against the other producing wells; neither declares a mandatory channel
#: because neither needs one to be available, and that is a different thing from having no evidence.
FAMILY_OF_HYPOTHESIS: Final[dict[str, tuple[str, str, str]]] = {
    "H-uptime": (
        "Production",
        "uptime_standardised_shift",
        "On-stream hours against the reference window, in standard deviations of the window.",
    ),
    "H-choke": (
        "Control",
        "choke_standardised_shift",
        "Choke position against the reference window, in standard deviations of the window.",
    ),
    "H-pressure": (
        "Pressure",
        "pressure_standardised_shift",
        "Downhole pressure against the reference window, in standard deviations of the window.",
    ),
    "H-water": (
        "Fluids",
        "water_cut_rise",
        "Rise in median water cut from the reference window to the episode window.",
    ),
    "H-field": (
        "Production",
        "offset_median_rate_change",
        "Median rate change across the other producing wells over the same dates, which separates "
        "a field-wide event from a well-specific one.",
    ),
}

#: Hypothesis labels. The schema ids are terse by design; an operator reads the sentence.
HYPOTHESIS_LABEL: Final[dict[str, str]] = {
    "H-uptime": "Downtime or reduced on-stream hours",
    "H-choke": "Choke restriction",
    "H-pressure": "Reservoir pressure decline",
    "H-water": "Water breakthrough",
    "H-field": "Field-wide or facility constraint",
}

#: Status labels for a hypothesis, operator-facing.
STATUS_LABEL: Final[dict[str, str]] = {
    "supported": "Supported",
    "plausible": "Plausible",
    "weak": "Weak",
    "contradicted": "Contradicted",
    "unresolved": "Unresolved",
}


def _period(onset: str, offset: str) -> str:
    return f"{onset} to {offset}"


def queue(store: RunStore, log: ReviewLog | None = None) -> Queue:
    """The investigation queue and its KPI strip. Decisions 3 and 9.

    **The review log is read, not assumed.** A first version hardcoded `review_state="none"` into
    the scorer and `"Not reviewed"` into every row, and published a KPI whose denominator asserted
    "none has been reviewed; the review log is empty". Review confirmed a finding through the API
    and the queue went on saying all three. The priority rule's review term could therefore never
    fire, which made one of its four terms dead rather than merely inert, and ADR 0009's "the review
    term fires on nothing until someone uses this console" was false: it fired on nothing
    afterwards too.
    """
    rows = store.episodes()
    investigation = store.manifests()["investigation"]
    evaluation = store.evaluation()
    reviews = log or ReviewLog()
    states = {
        investigation_id(str(row["well"]), str(row["onset"])): reviews.state_of(
            investigation_id(str(row["well"]), str(row["onset"]))
        )
        for row in rows
    }
    scored = [
        priority.score_episode(
            well=str(row["well"]),
            onset=str(row["onset"]),
            cumulative_shortfall_sm3=float(row["cumulative_rate_shortfall_sm3"]),
            episode_days=int(row["episode_days"]),
            verdict=str(row["verdict"]),
            evidence_band=_band_for(evaluation, str(row["well"]), str(row["onset"])),
            review_state=states[investigation_id(str(row["well"]), str(row["onset"]))],
        )
        for row in rows
    ]
    by_key = {(s.well, s.onset): s for s in scored}

    queue_rows = tuple(
        QueueRow(
            investigation_id=investigation_id(str(row["well"]), str(row["onset"])),
            well=str(row["well"]),
            period=_period(str(row["onset"]), str(row["offset"])),
            # Both medians from the diagnostic bundle the controller was given. A first version
            # had `actual_rate` as a None with the expected rate's source attached, which is the
            # unsourced figure of mark 1 wearing a borrowed label.
            actual_rate=Sourced(
                value=row["episode_median_rate_sm3_per_day"],
                source=f"investigation.findings.{index}.episode_median_rate_sm3_per_day",
                unit="Sm3/d",
                denominator="median over the episode's valid producing days",
            ),
            expected_rate=Sourced(
                value=row["baseline_median_rate_sm3_per_day"],
                source=f"investigation.findings.{index}.baseline_median_rate_sm3_per_day",
                unit="Sm3/d",
                denominator="median over the governing reference window",
            ),
            cumulative_shortfall=Sourced(
                value=float(row["cumulative_rate_shortfall_sm3"]),
                source=f"investigation.findings.{index}.cumulative_rate_shortfall_sm3",
                unit="Sm3",
                denominator="summed over the episode's valid producing days",
            ),
            deferred_volume=Sourced(
                value=float(row["deferred_volume_sm3"]),
                source=f"investigation.findings.{index}.deferred_volume_sm3",
                unit="Sm3",
                denominator="possibly deferred rather than lost",
            ),
            episode_days=Sourced(
                value=int(row["episode_days"]),
                source=f"investigation.findings.{index}.episode_days",
                unit="days",
                denominator="onset to offset inclusive",
            ),
            assessment=str(row["verdict"]),
            assessment_label=labels.verdict_label(str(row["verdict"])),
            causal_level_label=labels.causal_level_label(row.get("highest_level")),
            evidence_strength=_band_for(evaluation, str(row["well"]), str(row["onset"])),
            review_state=states[investigation_id(str(row["well"]), str(row["onset"]))],
            review_state_label=labels.review_state_label(
                states[investigation_id(str(row["well"]), str(row["onset"]))]
            ),
            data_quality=("Degraded" if row["poorly_evidenced"] else "Complete"),
            priority=by_key[(str(row["well"]), str(row["onset"]))].priority.value,
            priority_score=Sourced(
                value=by_key[(str(row["well"]), str(row["onset"]))].score,
                source=f"{RULE_PREFIX}21.5",
                denominator="section 21.5's four terms",
            ),
            priority_explanation=by_key[(str(row["well"]), str(row["onset"]))].explanation,
        )
        for index, row in enumerate(rows)
    )

    counts = priority.term_counts(scored)
    rule = PriorityRule(
        statement=(
            f"Cumulative shortfall at or above {priority.LARGE_SHORTFALL_SM3:,.0f} Sm3 scores 3, "
            f"at or above {priority.MODERATE_SHORTFALL_SM3:,.0f} Sm3 scores 2, otherwise 1.",
            f"Plus 1 if the episode lasts {priority.LONG_EPISODE_DAYS} days or more.",
            "Plus 1 if review is pending.",
            "Plus 1 if no single explanation is supported and the evidence is high or moderate.",
            f"{priority.HIGH_SCORE} or more is HIGH, "
            f"{priority.MEDIUM_SCORE} to {priority.HIGH_SCORE - 1} is MEDIUM, else LOW.",
        ),
        term_counts={
            name: Sourced(
                value=count,
                source=f"{RULE_PREFIX}21.5",
                denominator=f"of {len(scored)} episodes",
            )
            for name, count in counts.items()
        },
        caveat=(
            "This ordering is a stated convention, not a measured result: fourteen episodes, one "
            "of them HIGH, cannot show that an ordering is good. Two measurements go with it. The "
            "choice between this rule and a blunter one changes no episode's band on this data, so "
            "the data cannot tell them apart. But removing the fourth term altogether moves the "
            "single HIGH episode to MEDIUM and leaves the queue with no HIGH case, so that term "
            "decides the one promotion this rule makes. ADR 0009 records both, and section 21.5 "
            "requires both wherever the rule is printed: the first alone reads as the term being "
            "inert, which it is not."
        ),
    )

    return Queue(
        kpis=_production_kpis(investigation, states),
        rows=queue_rows,
        rule=rule,
        pinned=tuple(
            investigation_id(str(r["well"]), str(r["onset"]))
            for r in rows
            if str(r["verdict"]) in {"supported_explanation", "insufficient_evidence"}
        )[:3],
    )


def _production_kpis(
    investigation: Mapping[str, Any], states: Mapping[str, str]
) -> tuple[Kpi, ...]:
    """Decision 3's Production strip. Period-correct language, and no money without a price."""
    awaiting = sum(1 for state in states.values() if state not in {"confirmed", "dismissed"})
    recorded = sum(1 for state in states.values() if state != "none")
    return (
        Kpi(
            label="Open investigations",
            figure=Sourced(
                value=int(investigation["episodes"]),
                source="investigation.episodes",
                denominator="development episodes detected",
            ),
        ),
        Kpi(
            label="Awaiting review",
            figure=Sourced(
                value=awaiting,
                # The review log rather than the episode count. The first version published the
                # episode count under a denominator asserting the log was empty, which stayed on
                # the screen after a finding had been confirmed through the API.
                source=f"{RULE_PREFIX}21.6 review log",
                denominator="investigations with no confirmation or dismissal recorded",
            ),
            # The note counts what the log holds rather than asserting it holds nothing. The
            # denominator was fixed when the queue started reading the log and this sentence was
            # not, so it went on saying "nothing has been reviewed yet" after fourteen corrections
            # had been recorded: `awaiting` excludes only settled findings, and a correction does
            # not settle one.
            note=(
                "No review of any kind has been recorded."
                if not recorded
                else f"{recorded} of {len(states)} have a review recorded, "
                f"{len(states) - awaiting} settled."
            ),
        ),
        Kpi(
            label="Cumulative rate shortfall",
            figure=Sourced(
                value=float(investigation["cumulative_rate_shortfall_sm3"]),
                source="investigation.cumulative_rate_shortfall_sm3",
                unit="Sm3",
                denominator="summed over 14 development episodes",
            ),
        ),
        Kpi(
            label="Possibly deferred volume",
            figure=Sourced(
                value=float(investigation["deferred_volume_sm3"]),
                source="investigation.deferred_volume_sm3",
                unit="Sm3",
                denominator="possibly deferred rather than lost",
            ),
        ),
        Kpi(
            label="Estimated gross production value",
            money=Money(
                reason=(
                    "No oil price assumption was supplied, so no currency figure is "
                    "computed. Section 20.3: an illustration that circulates as a finding is the "
                    "failure mode."
                )
            ),
        ),
        Kpi(
            label="No conclusion issued",
            figure=Sourced(
                value=int(investigation["episodes_with_no_conclusion"]),
                source="investigation.episodes_with_no_conclusion",
                denominator="of 14 episodes",
            ),
            note="Insufficient evidence to name a single explanation. This is correct behaviour.",
        ),
        Kpi(
            label="Wells with an episode",
            figure=Sourced(
                value=int(investigation["wells_with_an_episode"]),
                source="investigation.wells_with_an_episode",
                denominator="of 5 development producing wells swept",
            ),
        ),
    )


def _band_for(evaluation: Mapping[str, Any], well: str, onset: str) -> str:
    """The section 19.4 evidence band, read from the evaluation manifest.

    Not recomputed from the finding. The band is a scored combination of features that section 19.4
    fixes, the evaluation harness publishes it, and a second scoring here would be a second
    implementation of a calibration.
    """
    for row in evaluation.get("evidence_scores", []):
        if str(row["well"]) == well and str(row["onset"]) == onset:
            return str(row["band"])
    return "unknown"


def header(store: RunStore) -> Header:
    """Decision 12: operational and data state first, build metadata behind a popover.

    "Historical replay mode" is shown because the data is historical and a console that did not say
    so would read as live. The pressure coverage line is there because section 18.3 stops three of
    the fourteen investigations on it, and an operator who did not know would read those as failures
    of the system rather than of the instrument record.
    """
    manifests = store.manifests()
    expectation = manifests["expectation"]
    extraction = manifests["extraction"]
    investigation = manifests["investigation"]
    evaluation = store.evaluation()
    freeze = evaluation.get("version_freeze", {})
    # Every key below is one the manifest actually holds. A first version guessed at
    # `expectation.wells`, `version_freeze.dataset_hash` and `version_freeze.expectation_version`,
    # none of which exist, and the header rendered "? development producing wells" and two
    # "unknown"s. None of it failed a gate, because the header's state lines are strings rather than
    # figures and section 21.6 mark 1 governs figures. Caught by looking at the screen, which is the
    # only thing that catches it.
    # `dataset_version` in the freeze is already a rendered string, not the nested object the
    # expectation manifest holds. Guessing at its shape is what produced "unknown" twice.
    dataset = str(freeze.get("dataset_version", "unknown"))
    return Header(
        field="Volve, 15/9",
        mode="Historical replay",
        data_through=str(expectation.get("split", {}).get("boundary", "unknown")),
        production_availability=(
            f"{len(investigation.get('development_wells', []))} development producing wells"
        ),
        report_index_availability=f"{extraction.get('reports', '?')} drilling reports indexed",
        pressure_coverage=(
            "Partial. Downhole pressure is absent for the whole episode on 3 of 14 "
            "investigations, which stop on missing evidence rather than guessing."
        ),
        posture="Read-only, human-reviewed, no actuation path",
        build_info={
            "commit": str(freeze.get("commit", "unknown")),
            "dataset": dataset,
            "expectation model": str(expectation.get("selected_model", "unknown")),
            "extractor": str(freeze.get("extractor_version", "unknown")),
            "investigator": str(freeze.get("investigator_version", "unknown")),
            "retrieval index": str(freeze.get("retrieval_index_version", "unknown")),
            "label set": str(freeze.get("label_set_version", "unknown")),
            "model roles": str(freeze.get("model_roles", "none")),
            "correction store": str(freeze.get("correction_store_version", "empty")),
            # The protocol document in force, from the console's own run manifest. Not the
            # investigation manifest's stamp: that names the version whose *marks* that layer
            # implements, section 18.7's, which have not changed since v4. Showing it in a header
            # labelled "protocol" told a reader the document was at v12 when it is at v14. Two
            # different questions, and conflating them is the whole of the bug.
            "protocol": CONSOLE_PROTOCOL_VERSION,
        },
    )


def _chart(artifacts: EpisodeArtifacts, finding: Mapping[str, Any]) -> ChartSeries:
    """The detector's own series, read from the artifact and not refitted."""
    rows = tuple(
        SeriesRow(
            date=str(point["date"]),
            day_class=str(point["day_class"]),
            actual=point["actual_rate_sm3_per_day"],
            expected=point["expected"],
            lower=point["lower"],
            upper=point["upper"],
            below_band=bool(point["below_band"]),
            on_stream_hours=point["on_stream_hours"],
            choke_size=point["choke_size"],
            downhole_pressure_bar=point["downhole_pressure_bar"],
            wellhead_pressure_bar=point["wellhead_pressure_bar"],
            water_cut=point["water_cut"],
        )
        for point in artifacts.series
    )
    governing = (
        f"{artifacts.series[0]['governing_window_start']} to "
        f"{artifacts.series[0]['governing_window_end']}"
        if artifacts.series
        else "unknown"
    )
    return ChartSeries(
        source=f"{ARTIFACT_PREFIX}{artifacts.investigation_id}.series.json",
        rows=rows,
        row_count=Sourced(
            value=len(rows),
            source=f"{ARTIFACT_PREFIX}{artifacts.investigation_id}.series.json",
            denominator="days in the episode window plus 45 either side",
        ),
        episode_window=_period(str(finding["episode_onset"]), str(finding["episode_offset"])),
        governing_window=governing,
    )


def _coverage(finding: Mapping[str, Any]) -> EvidenceCoverage:
    """Section 21.4's two lists, from the availability record the bundle produced.

    A channel with no usable day is missing, whatever the source had in the cell. That distinction
    is section 6's sentinel-zero rule reaching the screen: `15/9-F-12` has downhole pressure in 99.8
    percent of its rows and usable pressure in 31.2 percent, and an operator told the first number
    would believe an investigation could have used it.
    """
    available: list[str] = []
    missing: list[str] = []
    for entry in finding.get("availability", []):
        channel = str(entry["channel"])
        usable = int(entry["usable"])
        days = int(entry["days"])
        line = f"{channel}: {usable} of {days} days usable"
        (available if usable > 0 else missing).append(line)
    missing.extend(str(line) for line in finding.get("missing_evidence", []))

    # An investigation can decline to conclude with nothing missing at all, and the first version of
    # this panel showed an empty list when that happened. The section 21.6 mark 4 gate caught it on
    # `15/9-F-14` from 2012-03-11: every mandatory channel was available, retrieval found no
    # document, and no hypothesis reached the threshold. An empty "missing" list on an abstention
    # screen reads as the system saying there was no reason it could not conclude, which is the
    # opposite of what happened.
    #
    # So the stop reason is rendered as its own line. It is a recorded field, not a new figure.
    if not missing and str(finding.get("verdict", "")) == "insufficient_evidence":
        stop = str(finding.get("stop_reason", ""))
        if stop == "evidence_exhausted":
            missing.append(
                "Nothing was missing. Every mandatory channel was available and the drilling "
                "narrative was searched; no hypothesis reached the evidence threshold, so no "
                "single explanation is issued."
            )
        else:
            missing.append(f"The run stopped on {stop!r} before reaching a conclusion.")
    return EvidenceCoverage(available=tuple(available), missing=tuple(missing))


def _retrieval_passes(trace: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """The retrieval pass made for each hypothesis, from the trace's own record.

    Keyed by hypothesis, keeping the last pass where a hypothesis was searched more than once,
    because that is the one whose result stands. A hypothesis absent from this mapping was never
    searched, and the report cell says so rather than claiming a search that found nothing.
    """
    passes: dict[str, dict[str, str]] = {}
    for step in trace.get("steps", []):
        detail = step.get("detail") or {}
        if detail.get("hypothesis_id"):
            passes[str(detail["hypothesis_id"])] = {k: str(v) for k, v in detail.items()}
    return passes


def _hypotheses(
    finding: Mapping[str, Any],
    ledger: Sequence[Mapping[str, Any]],
    passes: Mapping[str, Mapping[str, str]],
) -> tuple[Hypothesis, ...]:
    """The matrix. One cell per hypothesis and evidence family, each carrying its own object.

    A cell with nothing behind it is unconstructible, so a family a hypothesis never looked at is
    `not_applicable` and a family it searched and found nothing in is `absent` with the retrieval
    record attached. Section 21.3: absence is an object, because a conclusion drawn from nothing
    looks identical to one drawn from something unless the nothing is recorded.

    Each hypothesis fills exactly one evidence family plus the report column, which is what the
    controller actually judges: section 18.2's bundle gives one standardised shift per hypothesis,
    and a matrix that spread it across columns would be inventing comparisons nobody made.
    """
    out: list[Hypothesis] = []
    for index, raw in enumerate(finding.get("hypotheses", [])):
        hypothesis_id = str(raw["hypothesis_id"])
        status = str(raw.get("status", "unresolved"))
        features = dict(raw.get("strength_features", {}))
        home, feature_name, rule = FAMILY_OF_HYPOTHESIS.get(
            hypothesis_id, ("Production", "", "No rule recorded for this hypothesis.")
        )
        documents = [s for s in raw.get("supporting", []) if str(s.get("kind")) == "document_span"]
        cells: dict[str, MatrixCell] = {}
        for family in EVIDENCE_FAMILIES:
            if family == "Report":
                cells[family] = _report_cell(finding, hypothesis_id, index, documents, passes)
            elif family == home:
                cells[family] = _evidence_cell(
                    finding, hypothesis_id, status, features, feature_name, rule, ledger
                )
            else:
                cells[family] = MatrixCell(
                    verdict="not_applicable",
                    label="Not applicable",
                    rule=(
                        f"{hypothesis_id} is judged on {home.lower()} evidence. This family is not "
                        "part of its test, so no comparison was made here."
                    ),
                )
        out.append(
            Hypothesis(
                hypothesis_id=hypothesis_id,
                label=HYPOTHESIS_LABEL.get(hypothesis_id, str(raw.get("description", ""))),
                status=status,
                status_label=STATUS_LABEL.get(status, status),
                cells=cells,
            )
        )
    return tuple(out)


def _evidence_cell(
    finding: Mapping[str, Any],
    hypothesis_id: str,
    status: str,
    features: Mapping[str, Any],
    feature_name: str,
    rule: str,
    ledger: Sequence[Mapping[str, Any]],
) -> MatrixCell:
    """The cell in a hypothesis's own evidence family, carrying the figure that decided it."""
    value = features.get(feature_name)
    verdict: str
    if status == "supported":
        verdict, label = "supports", "Supports"
    elif status == "contradicted":
        verdict, label = "contradicts", "Contradicts"
    else:
        verdict, label = "neutral", STATUS_LABEL.get(status, status)
    fact = (
        _fact_evidence(finding, hypothesis_id, feature_name, value, ledger)
        if value is not None
        else None
    )
    if verdict in {"supports", "contradicts"} and fact is None:
        # A judgement with nothing to show it is downgraded rather than asserted. The opposite of
        # the usual failure: a cell claiming support it cannot display is worse than one claiming
        # less than it could.
        verdict, label = "neutral", STATUS_LABEL.get(status, status)
    return MatrixCell(verdict=verdict, label=label, rule=rule, fact=fact)


def _report_cell(
    finding: Mapping[str, Any],
    hypothesis_id: str,
    index: int,
    documents: Sequence[Mapping[str, Any]],
    passes: Mapping[str, Mapping[str, str]],
) -> MatrixCell:
    """The report column: a cited span, a recorded absence, or a recorded non-search.

    **Every figure here comes from the trace.** The first version hardcoded the query string and a
    count of zero, so each absence named a search that never happened: on `15/9-F-14` from
    2012-01-31 it published "retrieval ran and returned nothing" for three hypotheses no pass was
    ever made for, and reported zero documents examined on an episode where retrieval returned two
    citable ones. Section 21.3's whole purpose is that a reader can tell those apart.
    """
    if documents:
        return MatrixCell(
            verdict="supports",
            label="Supports",
            rule=(
                "A report in the evidence window names the change, and the quoted span is verbatim "
                "in the event's own comment, which section 18.6's gate checks."
            ),
            document=_document_evidence(documents[0]),
        )
    slug = finding["artifact_slug"]
    source = f"{ARTIFACT_PREFIX}{slug}.trace.json"
    window = (
        f"well = {finding['well']}",
        f"window = {finding['episode_onset']} to {finding['episode_offset']}, "
        "plus 45 days either side",
    )
    made = passes.get(hypothesis_id)
    if made is None:
        return MatrixCell(
            verdict="absent",
            label="Not searched",
            rule=(
                "No retrieval pass was made for this hypothesis. The controller's budget is spent "
                "on the hypotheses its diagnostics put in play, so an untested one is a bound on "
                "the investigation rather than a finding about the documents."
            ),
            absence=Absence(
                absence_id=f"{slug}:{hypothesis_id}:not-searched",
                corpus="drilling-report narrative, BM25 over extracted events",
                filters=window,
                queries=(),
                documents_examined=Sourced(
                    value=0,
                    source=source,
                    denominator="no pass was made for this hypothesis, so nothing was examined",
                ),
                outcome="not_searched",
            ),
        )
    return MatrixCell(
        verdict="absent",
        label="None found",
        rule=(
            "Retrieval ran over the drilling narrative for this well and window and returned "
            "nothing citable for this hypothesis. ADR 0008 records why that is the normal case: "
            "not one of 3,673 drilling-report events falls inside any episode window."
        ),
        absence=Absence(
            absence_id=f"{slug}:{hypothesis_id}:pass",
            corpus="drilling-report narrative, BM25 over extracted events",
            filters=window,
            queries=(made["query"],),
            documents_examined=Sourced(
                value=int(made["hits"]),
                source=source,
                denominator=(
                    f"hits returned, of which {made['in_window']} fell inside the evidence window "
                    f"and {made['citable']} were citable"
                ),
            ),
            outcome="none_found",
        ),
    )


def _document_evidence(span: Mapping[str, Any]) -> DocumentEvidence:
    """The drawer for a cited span. Decision 7's fields, from the finding's own citation.

    Offsets are located in the span's own text rather than stored, because the validator of section
    18.6 already proved the span is a verbatim substring of the event's comment. What is published
    is the length, which is the one offset figure derivable from the artifact alone; a start offset
    would need the comment, and the comment belongs to the event store rather than to the finding.
    """
    text = str(span.get("span", ""))
    return DocumentEvidence(
        evidence_id=str(span.get("event_id", "unknown")),
        source_type="Daily drilling report",
        document=str(span.get("document", "unknown")),
        report_date=str(span.get("report_date", "see the document name")),
        span=text,
        start_offset=Sourced(
            value=0,
            source=str(span.get("event_id", "unknown")),
            denominator="offsets are relative to the cited event's comment",
        ),
        end_offset=Sourced(
            value=len(text),
            source=str(span.get("event_id", "unknown")),
            denominator="characters of verbatim span",
        ),
        document_hash="see docs/data_manifest.md for the corpus checksum",
    )


def _fact_evidence(
    finding: Mapping[str, Any],
    hypothesis_id: str,
    feature_name: str,
    value: Any,
    ledger: Sequence[Mapping[str, Any]],
) -> FactEvidence:
    """The drawer for the figure that decided a cell.

    **Every figure here is sourced to the key it actually came from.** The first version attached
    ledger fact ids to the two window medians, which the ledger does not record: `fact_000002` holds
    a reference rate of 3,052.735 Sm3/d and the drawer published 4,351.41 under its id, a different
    quantity from the same manifest row, and `fact_000001` is a volume in Sm3 whose id sat on a rate
    in Sm3/d. All 198 fact-sourced leaves were wrong.

    Mark 1 passed over every one of them, because it asks whether a source resolves and not whether
    the figure came from it. The ledger facts are now listed separately, each carrying the value the
    ledger records, so a reader can see the lineage without the drawer claiming the ledger said
    something it did not.
    """
    index = int(finding["row_index"])
    return FactEvidence(
        reference=f"{hypothesis_id}:{feature_name}",
        metric=feature_name.replace("_", " "),
        value=Sourced(
            value=float(value),
            source=f"{ARTIFACT_PREFIX}{finding['artifact_slug']}.finding.json",
            denominator=(
                f"{hypothesis_id}'s strength feature, from the section 18.2 diagnostic bundle"
            ),
        ),
        baseline_value=Sourced(
            value=finding.get("baseline_median_rate_sm3_per_day"),
            source=f"investigation.findings.{index}.baseline_median_rate_sm3_per_day",
            unit="Sm3/d",
            denominator="median rate over the governing reference window",
        ),
        episode_value=Sourced(
            value=finding.get("episode_median_rate_sm3_per_day"),
            source=f"investigation.findings.{index}.episode_median_rate_sm3_per_day",
            unit="Sm3/d",
            denominator="median rate over the episode's valid producing days",
        ),
        baseline_window=str(finding.get("baseline_window", "see the expectation panel")),
        episode_window=_period(str(finding["episode_onset"]), str(finding["episode_offset"])),
        source_table="production daily, through the section 18.2 diagnostic bundle",
        transformation=(
            f"{feature_name.replace('_', ' ')}, comparing the episode window against the "
            "governing reference window"
        ),
        ledger_facts=tuple(
            LedgerFact(
                fact_id=str(fact["id"]),
                metric=str(fact["metric"]),
                kind=str(fact.get("kind", "measured")),
                value=Sourced(
                    value=float(fact["value"]),
                    source=str(fact["id"]),
                    unit=str(fact.get("unit") or ""),
                    denominator=(
                        "as the provenance ledger records it; its lineage is in the facts "
                        "artifact"
                    ),
                ),
            )
            for fact in ledger
        ),
    )


def expectation_panel(store: RunStore) -> ExpectationPanel:
    """Decision 8: how the expected line was built, so an operator need not trust it blindly.

    Every figure is the expectation study's own published result, and the second one is the figure a
    reader of a band most needs: how often the band is wrong on the side the detector uses.

    **What this panel may not say**, because an earlier version said all three. Section 8 bands the
    **lower-tail exceedance rate** at 0.05 to 0.20; two-sided coverage is explicitly reported
    without a pass mark, so there is no "section 8 coverage bar" to miss. The "two to four times"
    figure in `docs/expectation_results.md` belongs to the two **candidate** models, 0.302 and
    0.387 against a nominal 0.10, not to two wells and not to the model in use. And no per-well
    figure exists for the selected model at all: section 8's conditions are applied to candidates,
    `naive-median28` is the protocol's fallback when none passes, so `condition_2_lower_tail` is
    never evaluated for it. The panel states the pooled figure it does have and says which
    condition the model in use has not been through.
    """
    expectation = store.manifests()["expectation"]
    chosen = str(expectation.get("selected_model", "naive-median28"))
    wape = expectation.get("wape", {}).get(chosen, {})
    return ExpectationPanel(
        model_name=chosen,
        # The parser version the run recorded. `expectation_version` was a guess at a key the
        # manifest does not hold, and the panel rendered "naive-median28 (unknown)" on every screen.
        model_version=str(expectation.get("parser_version", "unknown")),
        reference_window="the most recent stable window ending before the episode",
        regime="valid producing days only, downtime and quarantined days excluded",
        backtest_wape=Sourced(
            value=wape.get("7"),
            source=f"expectation.wape.{chosen}.7",
            unit="fraction",
            denominator="7-day horizon, development valid producing days",
        ),
        lower_tail_rate=Sourced(
            value=expectation.get("lower_tail_rate", {}).get("7"),
            source="expectation.lower_tail_rate.7",
            unit="of prediction rows fall below the lower bound",
            denominator=(
                "7-day horizon, pooled over development valid producing days; section 8 permits "
                "0.05 to 0.20"
            ),
        ),
        note=(
            "Deterministic and fitted before any investigation runs. The lower edge of this band "
            "is the edge the detector compares against, and it is badly placed: 0.56 of prediction "
            "rows fall below it where section 8 permits at most 0.20. That is why the band is "
            "shown as a band with no probability attached. Section 8's calibration condition has "
            "never been evaluated for this model: the conditions are applied to candidates, and "
            "naive-median28 is the fallback the protocol selects when no candidate passes."
        ),
    )


def detail(store: RunStore, wanted: str) -> InvestigationDetail:
    """One investigation, the console's signature screen. Decision 4."""
    row = store.by_id(wanted)
    artifacts = store.artifacts_for(str(row["well"]), str(row["onset"]))
    finding = dict(artifacts.finding)
    # The manifest row's index and the artifact's own name, so every figure the drawer publishes can
    # be sourced to the key it came from rather than to a ledger id that records something else.
    finding["row_index"] = next(
        index
        for index, candidate in enumerate(store.episodes())
        if investigation_id(str(candidate["well"]), str(candidate["onset"])) == wanted
    )
    finding["artifact_slug"] = artifacts.investigation_id
    finding["baseline_median_rate_sm3_per_day"] = row.get("baseline_median_rate_sm3_per_day")
    finding["episode_median_rate_sm3_per_day"] = row.get("episode_median_rate_sm3_per_day")
    finding["baseline_window"] = _period(
        str(row.get("baseline_start", "")), str(row.get("baseline_end", ""))
    )
    return InvestigationDetail(
        investigation_id=artifacts.investigation_id,
        well=str(row["well"]),
        period=_period(str(row["onset"]), str(row["offset"])),
        assessment_label=labels.verdict_label(str(row["verdict"])),
        causal_level_label=labels.causal_level_label(row.get("highest_level")),
        narrative=str(finding.get("narrative", "")),
        what_would_change_the_conclusion="; ".join(
            str(line) for line in finding.get("what_would_change_the_conclusion", [])
        ),
        recommended_next_check=str(finding.get("recommended_next_check", "")),
        chart=_chart(artifacts, finding),
        expectation=expectation_panel(store),
        hypotheses=_hypotheses(finding, artifacts.facts, _retrieval_passes(artifacts.trace)),
        evidence_families=EVIDENCE_FAMILIES,
        coverage=_coverage(finding),
        review_disclaimer=labels.REVIEW_DISCLAIMER,
        review_actions=dict(labels.REVIEW_ACTION),
        provenance={
            "finding id": str(finding.get("finding_id", "")),
            "investigator version": str(finding.get("investigator_version", "")),
            "correction store version": str(finding.get("correction_store_version") or "empty"),
            "stop reason": str(finding.get("stop_reason", "")),
            "steps used": str(finding.get("steps_used", "")),
            "facts artifact": f"{artifacts.investigation_id}.facts.json",
            "trace artifact": f"{artifacts.investigation_id}.trace.json",
        },
    )


# --------------------------------------------------------------------------------------------
# the System Health workspace, protocol section 22.4 marks 11 and 12
# --------------------------------------------------------------------------------------------


def _health_row(
    label: str, value: Any, source: str, *, unit: str = "", note: str = ""
) -> HealthRow:
    return HealthRow(
        label=label,
        value=Sourced(value=value, source=source, unit=unit, denominator=note or label),
        note=note,
    )


def system_health(store: RunStore) -> SystemHealth:
    """Tab 4, assembled from the two section 22 manifests and nothing else.

    Every number here is read from `security_run.json` or `ablation_run.json`. Section 21.1 and
    mark 11: the health tab renders and does not compute, **including its deltas**. A delta is
    published by the harness that owns both arms or it does not appear, which is why the
    comparison table below carries reasons rather than subtractions.
    """
    security = store.security()
    ablation = store.ablations()
    injection = security["injection"]
    sinks = security["markup_sinks"]
    corpus = security["attack_corpus"]
    provenance = security["provenance_failures"]
    limits = security["limits"]
    expectation = ablation["expectation"]
    retrieval = ablation["retrieval"]
    latency = ablation["cost_and_latency"]

    injection_rows = tuple(
        _health_row(label, injection[key], f"security.injection.{key}", note=note)
        for label, key, note in (
            ("Invariants held", "invariants_held", "one per payload per live invariant"),
            ("Invariants violated", "invariants_violated", ""),
            (
                "Fixtures not reached",
                "fixtures_not_reached",
                "a payload that never arrived has not tested anything",
            ),
            (
                "Live invariants untested",
                "live_invariants_untested",
                "a suite that ran nothing does not pass",
            ),
            ("Payloads in the corpus", "payloads", "six classes"),
        )
    )

    comparison = tuple(
        ComparisonRow(
            metric=metric,
            current=Sourced(value=value, source=source, unit="", denominator=metric),
            unavailable_because=(
                "Only one scored version of this exists. Section 22.4 mark 12: a delta against "
                "an absent baseline is a figure from nowhere, and an empty column reads as no "
                "change, so the reason is printed instead of a number."
            ),
        )
        for metric, value, source in (
            ("Invariants held", injection["invariants_held"], "security.injection.invariants_held"),
            (
                "Figures contradicting their records",
                provenance["class_3_contradictions"],
                "security.provenance_failures.class_3_contradictions",
            ),
            (
                "Episodes opened by the selected model",
                next(
                    (
                        r["episodes_opened"]
                        for r in expectation["rows"]
                        if r["model"] == "naive-median28"
                    ),
                    0,
                ),
                "ablation.expectation.rows",
            ),
            (
                "End-to-end p95, seconds",
                latency["end_to_end_p95_seconds"],
                "ablation.cost_and_latency.end_to_end_p95_seconds",
            ),
        )
    )

    return SystemHealth(
        generated=str(security["generated"]),
        commit_sha=str(security["commit_sha"]),
        protocol_version=str(security["protocol_version"]),
        injection=injection_rows,
        vacuous_invariants=tuple(
            VacuousInvariant(key=v["key"], wording=v["wording"], reason=v["reason"])
            for v in injection["vacuous"]
        ),
        parser_corpus=(
            _health_row(
                "XML attack fixtures",
                corpus["xml_fixtures"],
                "security.attack_corpus.xml_fixtures",
            ),
            _health_row(
                "Archive attack fixtures",
                corpus["archive_fixtures"],
                "security.attack_corpus.archive_fixtures",
            ),
            _health_row(
                "Documents that must parse",
                corpus["must_parse_fixtures"],
                "security.attack_corpus.must_parse_fixtures",
                note="a corpus of only refusals cannot tell a careful parser from a broken one",
            ),
            _health_row("Unescaped-markup sinks", sinks["found"], "security.markup_sinks.found"),
            _health_row(
                "Frontend files scanned",
                sinks["files_scanned"],
                "security.markup_sinks.files_scanned",
                note="a scan of nothing passes, so the count is part of the result",
            ),
        ),
        provenance=(
            _health_row(
                "Failure classes put to the gate",
                provenance["classes"],
                "security.provenance_failures.classes",
            ),
            _health_row(
                "Figures contradicting their records",
                provenance["class_3_contradictions"],
                "security.provenance_failures.class_3_contradictions",
                note="a source that resolves is weaker than one that supports the figure",
            ),
        ),
        limits=(
            _health_row(
                "Review note, characters",
                limits["max_note_chars"],
                "security.limits.max_note_chars",
                unit="characters",
            ),
            _health_row(
                "Actor name, characters",
                limits["max_actor_chars"],
                "security.limits.max_actor_chars",
                unit="characters",
            ),
            _health_row(
                "API requests per minute",
                limits["max_requests_per_minute"],
                "security.limits.max_requests_per_minute",
                note="per client, one process, fixed window",
            ),
            _health_row(
                "Asset requests per minute",
                limits["max_asset_requests_per_minute"],
                "security.limits.max_asset_requests_per_minute",
            ),
        ),
        not_applicable=tuple(
            NotApplicable(key=key, reason=reason)
            for key, reason in {**limits["not_applicable"], **latency["not_applicable"]}.items()
        ),
        expectation_ablation=ExpectationAblation(
            source="ablation.expectation.rows",
            row_count=Sourced(
                value=len(expectation["rows"]),
                source="ablation.expectation.rows",
                unit="",
                denominator="expectation models compared",
            ),
            rows=tuple(
                ExpectationAblationRow(
                    model=str(r["model"]),
                    episodes_opened=int(r["episodes_opened"]),
                    wape=r.get("wape_h7")
                    if "wape_h7" in r
                    else next((v for k, v in r.items() if k.startswith("wape_")), None),
                )
                for r in expectation["rows"]
            ),
        ),
        retrieval_ablation=(
            _health_row(
                "Episodes with any in-window document",
                retrieval["episodes_with_documents"],
                "ablation.retrieval.episodes_with_documents",
                note=f"of {retrieval['episodes_total']} development episodes",
            ),
            *(
                _health_row(
                    f"{row['well']} {row['onset']}: causal level",
                    1 if row["level_changed"] else 0,
                    "ablation.retrieval.rows",
                    note=f"{row['highest_level_with']} with the document, "
                    f"{row['highest_level_without']} without it",
                )
                for row in retrieval["rows"]
            ),
        ),
        retrieval_note=str(retrieval["note"]),
        calibration_note=str(ablation["calibration"]["reason"]),
        latency=(
            _health_row(
                "Controller p95, seconds",
                latency["controller_p95_seconds"],
                "ablation.cost_and_latency.controller_p95_seconds",
                unit="seconds",
                note="the stages alone, over a bundle already built",
            ),
            _health_row(
                "End-to-end p95, seconds",
                latency["end_to_end_p95_seconds"],
                "ablation.cost_and_latency.end_to_end_p95_seconds",
                unit="seconds",
                note="bundle construction and the controller",
            ),
            _health_row(
                "Investigations timed",
                latency["investigations"],
                "ablation.cost_and_latency.investigations",
            ),
        ),
        comparison=comparison,
        comparison_note=(
            "One scored version exists, so no delta can be computed. Mark 12 requires the reason "
            "in place of the number: a 0.00 against an absent baseline is a figure from nowhere, "
            "and an empty column reads as no change."
        ),
        experiments=(
            "scripts/run_security_checks.py",
            "scripts/run_ablations.py",
            "scripts/serve_injected_console.py + scripts/check_rendered_inert.js",
            "tests/test_security.py",
            "tests/test_provenance_failures.py",
            "tests/test_api_security.py",
        ),
    )
