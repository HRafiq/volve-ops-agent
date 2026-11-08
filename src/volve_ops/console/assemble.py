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

from collections.abc import Mapping
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

#: The columns of the hypothesis and evidence matrix, in the order the console design shows them.
#: A presentation choice, not a figure: these group the channels section 18.2 already defines.
EVIDENCE_FAMILIES: Final[tuple[str, ...]] = (
    "Production",
    "Control",
    "Pressure",
    "Fluids",
    "Report",
)

#: Which family a mandatory channel belongs to. Channels the bundle names, grouped for display.
FAMILY_OF_CHANNEL: Final[dict[str, str]] = {
    "on_stream_hours": "Production",
    "choke_size": "Control",
    "choke_dp_bar": "Control",
    "downhole_pressure_bar": "Pressure",
    "wellhead_pressure_bar": "Pressure",
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
    evaluation = store.evaluation()
    freeze = evaluation.get("version_freeze", {})
    return Header(
        field="Volve, 15/9",
        mode="Historical replay",
        data_through=str(expectation.get("split", {}).get("boundary", "unknown")),
        production_availability=f"{expectation.get('wells', '?')} development producing wells",
        report_index_availability=f"{extraction.get('reports', '?')} drilling reports indexed",
        pressure_coverage=(
            "Partial. Downhole pressure is absent for the whole episode on 3 of 14 "
            "investigations, which stop on missing evidence rather than guessing."
        ),
        posture="Read-only, human-reviewed, no actuation path",
        build_info={
            "commit": str(freeze.get("commit", "unknown")),
            "dataset": str(freeze.get("dataset_hash", "unknown")),
            "expectation model": str(freeze.get("expectation_version", "unknown")),
            "retrieval index": str(freeze.get("retrieval_index_version", "unknown")),
            "model roles": str(freeze.get("model_roles", "none")),
            "correction store": str(freeze.get("correction_store_version", "empty")),
            "protocol": str(manifests["investigation"].get("protocol_version", "unknown")),
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
    """
    out: list[Hypothesis] = []
    for index, raw in enumerate(finding.get("hypotheses", [])):
        hypothesis_id = str(raw["hypothesis_id"])
        required = {str(c) for c in raw.get("required_channels", [])}
        families = {FAMILY_OF_CHANNEL[c] for c in required if c in FAMILY_OF_CHANNEL}
        supporting = list(raw.get("supporting", []))
        documents = [s for s in supporting if str(s.get("kind")) == "document_span"]
        cells: dict[str, MatrixCell] = {}
        for family in EVIDENCE_FAMILIES:
            if family == "Report":
                if documents:
                    first = documents[0]
                    cells[family] = MatrixCell(
                        verdict="supports",
                        label="Supports",
                        rule=(
                            "A report in the evidence window names the change, and the quoted span "
                            "is verbatim in the event's own comment."
                        ),
                        document=_document_evidence(first),
                    )
                else:
                    cells[family] = MatrixCell(
                        verdict="absent",
                        label="None found",
                        rule=(
                            "Retrieval ran over the drilling narrative for this well and window "
                            "and returned nothing that names a reason."
                        ),
                        absence=Absence(
                            absence_id=f"absence_{hypothesis_id}_{index}",
                            corpus="drilling-report narrative, BM25 over extracted events",
                            filters=(
                                f"well = {finding['well']}",
                                f"window = {finding['episode_onset']} "
                                f"to {finding['episode_offset']}, plus 45 days either side",
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
                continue
            if family not in families:
                cells[family] = MatrixCell(
                    verdict="not_applicable",
                    label="Not applicable",
                    rule="This hypothesis declares no mandatory channel in this family.",
                )
                continue
            status = str(raw.get("status", "unresolved"))
            if status == "contradicted":
                verdict, label = "contradicts", "Contradicts"
            elif status == "supported":
                verdict, label = "supports", "Supports"
            else:
                verdict, label = "neutral", STATUS_LABEL.get(status, status)
            fact = _fact_evidence(finding, family, fact_ids)
            if verdict in {"supports", "contradicts"} and fact is None:
                verdict, label = "neutral", STATUS_LABEL.get(status, status)
            cells[family] = MatrixCell(
                verdict=verdict,
                label=label,
                rule=(
                    "The channel moved with the direction and timing the hypothesis predicts, "
                    "comparing the episode window against the governing reference window."
                ),
                fact=fact,
            )
        out.append(
            Hypothesis(
                hypothesis_id=hypothesis_id,
                label=HYPOTHESIS_LABEL.get(hypothesis_id, str(raw.get("description", ""))),
                status=str(raw.get("status", "unresolved")),
                status_label=STATUS_LABEL.get(str(raw.get("status", "")), "Unresolved"),
                cells=cells,
            )
        )
    return tuple(out)


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
    finding: Mapping[str, Any], family: str, fact_ids: frozenset[str]
) -> FactEvidence | None:
    """The drawer for a fact, when the finding cites one the ledger defines.

    Returns None when it does not, and the caller then downgrades the cell to neutral rather than
    asserting a judgement with nothing behind it. That is the opposite of the usual failure here: a
    cell that claims support it cannot show is worse than a cell that claims less than it could.
    """
    wanted = str(finding.get("shortfall_fact_id") or "")
    if family != "Production" or wanted not in fact_ids:
        return None
    return FactEvidence(
        fact_id=wanted,
        metric="episode rate shortfall",
        baseline_value=Sourced(
            value=finding.get("baseline_median_rate_sm3_per_day"),
            source=str(finding.get("expected_volume_fact_id") or wanted),
            unit="Sm3/d",
            denominator="median over the governing reference window",
        ),
        episode_value=Sourced(
            value=finding.get("episode_median_rate_sm3_per_day"),
            source=str(finding.get("actual_volume_fact_id") or wanted),
            unit="Sm3/d",
            denominator="median over the episode's valid producing days",
        ),
        baseline_window=str(finding.get("baseline_window", "see the expectation panel")),
        episode_window=_period(
            str(finding["episode_onset"]), str(finding["episode_offset"])
        ),
        source_table="production daily, via the episode detector",
        transformation="median rate per valid producing day, differenced against the expectation",
        input_records=Sourced(
            value=None,
            source=wanted,
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
        model_version=str(expectation.get("expectation_version", "unknown")),
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
