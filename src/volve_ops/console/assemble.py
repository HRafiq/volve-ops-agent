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
from typing import Any, Final

from volve_ops.console import labels, priority
from volve_ops.console.payloads import (
    Absence,
    ChartSeries,
    DocumentEvidence,
    EvidenceCoverage,
    ExpectationPanel,
    FactEvidence,
    Header,
    Hypothesis,
    InvestigationDetail,
    Kpi,
    MatrixCell,
    Money,
    PriorityRule,
    Queue,
    QueueRow,
    SeriesRow,
)
from volve_ops.console.sources import ARTIFACT_PREFIX, RULE_PREFIX, Sourced
from volve_ops.console.store import EpisodeArtifacts, RunStore, investigation_id

#: The protocol document version this console was built against. Section 21 and its amendments.
CONSOLE_PROTOCOL_VERSION: Final[str] = "v14"

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


def queue(store: RunStore) -> Queue:
    """The investigation queue and its KPI strip. Decisions 3 and 9."""
    rows = store.episodes()
    investigation = store.manifests()["investigation"]
    evaluation = store.evaluation()
    scored = [
        priority.score_episode(
            well=str(row["well"]),
            onset=str(row["onset"]),
            cumulative_shortfall_sm3=float(row["cumulative_rate_shortfall_sm3"]),
            episode_days=int(row["episode_days"]),
            verdict=str(row["verdict"]),
            evidence_band=_band_for(evaluation, str(row["well"]), str(row["onset"])),
            review_state="none",
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
            review_state="Not reviewed",
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
            "This ordering is a stated convention, not a measured result. Fourteen "
            "episodes, one of them HIGH, cannot show an ordering is good. The review term fires on "
            "nothing until someone uses this console, and the choice between this rule and a "
            "blunter one changes no episode's band on this data. ADR 0009 records both."
        ),
    )

    return Queue(
        kpis=_production_kpis(investigation),
        rows=queue_rows,
        rule=rule,
        pinned=tuple(
            investigation_id(str(r["well"]), str(r["onset"]))
            for r in rows
            if str(r["verdict"]) in {"supported_explanation", "insufficient_evidence"}
        )[:3],
    )


def _production_kpis(investigation: Mapping[str, Any]) -> tuple[Kpi, ...]:
    """Decision 3's Production strip. Period-correct language, and no money without a price."""
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
                value=int(investigation["episodes"]),
                source="investigation.episodes",
                denominator="none has been reviewed; the review log is empty",
            ),
            note="No investigation has been reviewed yet, so every one is awaiting review.",
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


def _hypotheses(finding: Mapping[str, Any], fact_ids: frozenset[str]) -> tuple[Hypothesis, ...]:
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
                cells[family] = _report_cell(finding, hypothesis_id, index, documents)
            elif family == home:
                cells[family] = _evidence_cell(
                    finding, hypothesis_id, status, features, feature_name, rule, fact_ids
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
    fact_ids: frozenset[str],
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
        _fact_evidence(finding, hypothesis_id, feature_name, value, fact_ids)
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
) -> MatrixCell:
    """The report column: a cited span, or a recorded absence with the search behind it."""
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
    return MatrixCell(
        verdict="absent",
        label="None found",
        rule=(
            "Retrieval ran over the drilling narrative for this well and window and returned "
            "nothing naming a reason. ADR 0008 records why that is the normal case: not one of "
            "3,673 drilling-report events falls inside any episode window."
        ),
        absence=Absence(
            absence_id=f"absence_{hypothesis_id}_{index}",
            corpus="drilling-report narrative, BM25 over extracted events",
            filters=(
                f"well = {finding['well']}",
                f"window = {finding['episode_onset']} to {finding['episode_offset']}, "
                "plus 45 days either side",
            ),
            queries=(f"terms derived from {hypothesis_id}",),
            documents_examined=Sourced(
                value=0,
                source=f"{RULE_PREFIX}18.6 retrieval record",
                denominator="documents returned for this hypothesis",
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
    fact_ids: frozenset[str],
) -> FactEvidence | None:
    """The drawer for the figure that decided a cell.

    The figure is the hypothesis's own strength feature, which section 18.2's bundle computed from
    the two windows. It is sourced to the finding's shortfall fact when the ledger defines one, and
    the drawer prints the two window medians beside it so a reader can see what moved.
    """
    anchor = str(finding.get("shortfall_fact_id") or "")
    source = anchor if anchor in fact_ids else f"{RULE_PREFIX}18.2 diagnostic bundle"
    return FactEvidence(
        fact_id=anchor or f"{hypothesis_id}:{feature_name}",
        metric=feature_name.replace("_", " "),
        baseline_value=Sourced(
            value=finding.get("baseline_median_rate_sm3_per_day"),
            source=str(finding.get("expected_volume_fact_id") or source),
            unit="Sm3/d",
            denominator="median rate over the governing reference window",
        ),
        episode_value=Sourced(
            value=finding.get("episode_median_rate_sm3_per_day"),
            source=str(finding.get("actual_volume_fact_id") or source),
            unit="Sm3/d",
            denominator="median rate over the episode's valid producing days",
        ),
        baseline_window=str(finding.get("baseline_window", "see the expectation panel")),
        episode_window=_period(str(finding["episode_onset"]), str(finding["episode_offset"])),
        source_table="production daily, through the section 18.2 diagnostic bundle",
        transformation=(
            f"{feature_name.replace('_', ' ')} = {float(value):.4g}, comparing the episode window "
            "against the governing reference window"
        ),
        input_records=Sourced(
            value=None,
            source=source,
            denominator="walk the fact's lineage in the facts artifact",
        ),
        derived_facts=tuple(
            str(finding[key])
            for key in ("actual_volume_fact_id", "expected_volume_fact_id", "shortfall_fact_id")
            if finding.get(key)
        ),
    )


def expectation_panel(store: RunStore) -> ExpectationPanel:
    """Decision 8: how the expected line was built, so an operator need not trust it blindly.

    Every figure is the expectation study's own published result. The WAPE is the selected model's,
    and the interval coverage is the figure that **failed** its pre-registered bar: section 8's
    calibration mark is not met, by two to four times, and the panel says so where the line is
    drawn rather than in a document nobody opens.
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
        interval_coverage=Sourced(
            value=expectation.get("lower_tail_rate", {}).get("7"),
            source="expectation.lower_tail_rate.7",
            unit="fraction of evaluated days below the lower bound",
            denominator=(
                "7-day horizon; section 8 accepts 0.05 to 0.20, so this is the mark that fails"
            ),
        ),
        note=(
            "Deterministic and fitted before any investigation runs. The interval does not "
            "calibrate: section 8's coverage bar is missed by two to four times on both qualifying "
            "wells, which is why the band is shown as a band and no probability is attached to it."
        ),
    )


def detail(store: RunStore, wanted: str) -> InvestigationDetail:
    """One investigation, the console's signature screen. Decision 4."""
    row = store.by_id(wanted)
    artifacts = store.artifacts_for(str(row["well"]), str(row["onset"]))
    finding = dict(artifacts.finding)
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
        hypotheses=_hypotheses(finding, artifacts.fact_ids),
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
