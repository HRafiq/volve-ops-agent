"""The declared rows of the development results table, per protocol section 19.3.

This is the project's statement of what it measures, in one place, and it is data rather than code
so that a reader can audit the list without following any logic.

Every row names its denominator, because this project has already published a coverage figure that
differs by two points depending on the population it is taken over, and a reader who cannot see the
denominator cannot reconcile a table against a document.

`deferred` rows carry no value and name what would settle them. There are more of them than a reader
might expect, and they are not placeholders: each is a metric the plan asked for that this
dataset or this project's circumstances do not support, recorded so the absence is a decision
rather than an omission.
"""

from __future__ import annotations

from typing import Final

from volve_ops.evaluation.table import MetricRow, Status

#: What would settle the metrics needing a reader with drilling-operations experience. Written once
#: because it is the same obstacle in four places, and section 18.8 already says it twice.
_NEEDS_A_DOMAIN_READER: Final[str] = (
    "an adjudication by a reader with drilling-operations experience, per protocol section 17.4"
)

ROWS: Final[tuple[MetricRow, ...]] = (
    # ------------------------------------------------------------------ data and split
    MetricRow(
        layer="Data and split",
        metric="Drilling reports read",
        manifest="extraction",
        key="reports",
        denominator="WITSML drill reports in the share",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Data and split",
        metric="Leakage audit, five checks of section 19.2",
        manifest=None,
        key=None,
        denominator="computed by the harness, not a manifest",
        status=Status.GATED,
        note="reported in the harness output rather than a run manifest",
    ),
    # ------------------------------------------------------------------ expectation
    MetricRow(
        layer="Expectation engine",
        metric="Episodes opened on development data",
        manifest="expectation",
        key="episodes",
        denominator="development days of 6 producing wells",
        status=Status.REPORTED,
        note="one detector, two wells carry all of them; not a benchmark, per section 19.11",
    ),
    *(
        MetricRow(
            layer="Expectation engine",
            metric=f"Days evaluated, {model}",
            manifest="expectation",
            key=f"evaluated_days.{model}",
            denominator="development valid producing days with a fitted window",
            status=Status.REPORTED,
        )
        for model in (
            "naive-median28",
            "naive-persistence",
            "exponential-decline",
            "hyperbolic-decline",
            "choke-scaled",
        )
    ),
    MetricRow(
        layer="Expectation engine",
        metric="Interval coverage within the section 8 band",
        manifest=None,
        key=None,
        denominator="development valid producing days, 2 wells reaching the 150-day gate",
        status=Status.DEFERRED,
        settled_by="an interval construction that calibrates; the current one fails by 2 to 4 "
        "times and the failure is reported in docs/expectation_results.md",
    ),
    MetricRow(
        layer="Expectation engine",
        metric="Episode precision and recall",
        manifest=None,
        key=None,
        denominator="would need a curated episode set",
        status=Status.DEFERRED,
        settled_by="a curated episode set; section 19.11 declines to manufacture one from 14 "
        "episodes on 2 wells",
    ),
    # ------------------------------------------------------------------ extraction
    MetricRow(
        layer="Drilling-report extraction",
        metric="Non-productive events extracted",
        manifest="extraction",
        key="events",
        denominator="23,447 activity blocks",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Drilling-report extraction",
        metric="Narrative chunks indexed",
        manifest="extraction",
        key="indexed_chunks",
        denominator="one per extracted event comment",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Drilling-report extraction",
        metric="Section 14.3 event detection is exact",
        manifest="labels",
        key="section_14_3.detection_exact",
        denominator="617 qualifying blocks in the labelled sample's 99 documents",
        status=Status.GATED,
    ),
    MetricRow(
        layer="Drilling-report extraction",
        metric="Section 14.3 duration is exact",
        manifest="labels",
        key="section_14_3.duration_exact",
        denominator="617 qualifying blocks, to within one minute",
        status=Status.GATED,
    ),
    MetricRow(
        layer="Drilling-report extraction",
        metric="Qualifying blocks checked",
        manifest="labels",
        key="section_14_3.qualifying_blocks",
        denominator="blocks meeting the section 14.1 rule in those documents",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Drilling-report extraction",
        metric="Events checked against the source",
        manifest="labels",
        key="section_14_3.events_checked",
        denominator="as above; equality with it is the detection pass mark",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Drilling-report extraction",
        metric="Documents walked independently of the extractor",
        manifest="labels",
        key="section_14_3.documents",
        denominator="source documents of the labelled sample",
        status=Status.REPORTED,
    ),
    # ------------------------------------------------------------------ cause labels
    MetricRow(
        layer="Cause labels",
        metric="Labels in the development set",
        manifest="labels",
        key="label_count",
        denominator="the section 16 stratified draw, target 120 to 150",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Cause labels",
        metric="Expert labels",
        manifest="labels",
        key="expert_labels",
        denominator="of the 135; the rest are machine-assisted per section 17",
        status=Status.REPORTED,
        note="zero, which is what suspends the section 14.5 selection gate",
    ),
    MetricRow(
        layer="Cause labels",
        metric="Selection permitted by section 17.2",
        manifest="labels",
        key="selection_permitted",
        denominator="false while any label is machine-assisted",
        status=Status.GATED,
        note="gated in the sense that the code refuses selection, not that false is a failure",
    ),
    MetricRow(
        layer="Cause labels",
        metric="Events with a stated cause",
        manifest="labels",
        key="stated_cause_events",
        denominator="135 labelled events",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Cause labels",
        metric="Spans cited, all verbatim",
        manifest="labels",
        key="spans_cited",
        denominator="one per attributed label; verbatim checked on every read",
        status=Status.GATED,
    ),
    MetricRow(
        layer="Cause labels",
        metric="Rows carrying a note",
        manifest="labels",
        key="rows_with_a_note",
        denominator="135 labelled events",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Cause labels",
        metric="Notes naming a rejected alternative label",
        manifest="labels",
        key="rows_naming_another_label_in_the_note",
        denominator="the 55 rows carrying a note",
        status=Status.REPORTED,
    ),
    *(
        MetricRow(
            layer="Cause labels",
            metric=f"{name} macro-F1",
            manifest="labels",
            key=f"baselines.{name}.macro_f1",
            denominator="5 classes clearing the 5-instance floor, of 135 events",
            status=Status.REPORTED,
            note="reported, not gated: section 17.2 suspends the selection gate",
        )
        for name in ("echo-subcategory", "echo-statedetail")
    ),
    *(
        MetricRow(
            layer="Cause labels",
            metric=f"{name} exact agreement",
            manifest="labels",
            key=f"baselines.{name}.exact_agreement",
            denominator="135 labelled events",
            status=Status.REPORTED,
        )
        for name in ("echo-subcategory", "echo-statedetail")
    ),
    *(
        MetricRow(
            layer="Cause labels",
            metric=f"{name} classes in the macro average",
            manifest="labels",
            key=f"baselines.{name}.classes_in_average",
            denominator="of 12 taxonomy classes; 2 are unreachable per the guide",
            status=Status.REPORTED,
        )
        for name in ("echo-subcategory", "echo-statedetail")
    ),
    MetricRow(
        layer="Cause labels",
        metric="The two baselines agree with each other",
        manifest="labels",
        key="baseline_mutual_agreement",
        denominator="135 labelled events",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Cause labels",
        metric="Labels match the baselines' consensus",
        manifest="labels",
        key="labels_match_baseline_consensus",
        denominator="the 60 events where both baselines agree",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Cause labels",
        metric="Consensus is `not_stated`",
        manifest="labels",
        key="baseline_consensus_abstained",
        denominator="the 60 events where both baselines agree",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Cause labels",
        metric="Of those, labels name a cause",
        manifest="labels",
        key="baseline_consensus_abstained_labels_name_a_cause",
        denominator="the 44 where the consensus abstains",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Cause labels",
        metric="Consensus names a cause",
        manifest="labels",
        key="baseline_consensus_asserted",
        denominator="the 60 events where both baselines agree",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Cause labels",
        metric="Of those, labels agree",
        manifest="labels",
        key="baseline_consensus_asserted_labels_agree",
        denominator="the 16 where the consensus names a cause",
        status=Status.REPORTED,
        note="one of sixteen; unresolved and published as unresolved",
    ),
    MetricRow(
        layer="Cause labels",
        metric="Source coding flagged as disagreeing with the comment",
        manifest="labels",
        key="source_coding_flagged",
        denominator="135 labelled events; judgement-based, criterion in the guide",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Cause labels",
        metric="Source coding disagreement rate",
        manifest="labels",
        key="source_coding_flagged_rate",
        denominator="as above",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Cause labels",
        metric="Subcategory names a cause that is not the label",
        manifest="labels",
        key="subcategory_names_a_cause_that_is_not_the_label",
        denominator="135 labelled events; the mechanical companion, needing no judgement",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Cause labels",
        metric="Cause attribution macro-F1 against a selected approach",
        manifest=None,
        key=None,
        denominator="would need expert labels",
        status=Status.DEFERRED,
        settled_by=_NEEDS_A_DOMAIN_READER + ", at 80 percent agreement on the 40 drawn events",
    ),
    MetricRow(
        layer="Cause labels",
        metric="Inter-pass label agreement",
        manifest=None,
        key=None,
        denominator="withdrawn",
        status=Status.DEFERRED,
        settled_by="nothing; protocol amendment 2 withdrew it, because re-running a model over the "
        "same comments does not estimate a person's consistency with themselves",
    ),
    # ------------------------------------------------------------------ retrieval
    MetricRow(
        layer="Retrieval",
        metric="Chunks in the index at investigation time",
        manifest="investigation",
        key="indexed_chunks",
        denominator="one per extracted event comment",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Retrieval",
        metric="Evidence window either side of an episode",
        manifest="investigation",
        key="evidence_window_days",
        denominator="days; post-inspection per amendment 4, and outcome-determining",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Retrieval",
        metric="Recall at k against a gold evidence set",
        manifest=None,
        key=None,
        denominator="would need a gold evidence set",
        status=Status.DEFERRED,
        settled_by="the curated episode set section 15 defers, and a gold evidence set built from "
        "it; neither exists and section 15 declines to fix a threshold against either",
    ),
    # ------------------------------------------------------------------ investigation
    MetricRow(
        layer="Investigation",
        metric="Episodes investigated",
        manifest="investigation",
        key="episodes",
        denominator="all development episodes from the section 9 detector",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Investigation",
        metric="All five section 18.7 gates pass",
        manifest="investigation",
        key="all_pass",
        denominator="14 findings",
        status=Status.GATED,
        note="two of the five have little on this corpus to examine; "
        "docs/investigation_results.md says which",
    ),
    MetricRow(
        layer="Investigation",
        metric="Document citations",
        manifest="investigation",
        key="document_citations",
        denominator="across all 14 findings",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Investigation",
        metric="Findings reaching `documented_root_cause`",
        manifest="investigation",
        key="documented_root_cause_reached",
        denominator="14 findings",
        status=Status.REPORTED,
        note="one; ADR 0008 records why it is rare rather than impossible",
    ),
    MetricRow(
        layer="Investigation",
        metric="Agreement with `strongest-deviation` on the driver family",
        manifest="investigation",
        key="baseline_agreement.agree",
        denominator="the episodes where both named a driver",
        status=Status.REPORTED,
        note="the two share most of their implementation, so this largely measures shared code",
    ),
    MetricRow(
        layer="Investigation",
        metric="Episodes where both named a driver",
        manifest="investigation",
        key="baseline_agreement.comparable",
        denominator="14 episodes; the baseline abstains on 7",
        status=Status.REPORTED,
    ),
    MetricRow(
        layer="Investigation",
        metric="False root-cause claims, mechanical half",
        manifest=None,
        key=None,
        denominator="findings claiming a documented root cause; computed by the harness",
        status=Status.GATED,
    ),
    MetricRow(
        layer="Investigation",
        metric="False root-cause rate, the half needing a reader",
        manifest=None,
        key=None,
        denominator="would need correctness",
        status=Status.DEFERRED,
        settled_by=_NEEDS_A_DOMAIN_READER
        + "; section 19.5 fixes the 5-to-1 weighting against an abstention now",
    ),
    MetricRow(
        layer="Investigation",
        metric="Hypothesis-set precision, recall and F1",
        manifest=None,
        key=None,
        denominator="would need gold hypothesis sets",
        status=Status.DEFERRED,
        settled_by=_NEEDS_A_DOMAIN_READER,
    ),
    MetricRow(
        layer="Investigation",
        metric="Risk and coverage curve",
        manifest=None,
        key=None,
        denominator="would need correctness",
        status=Status.DEFERRED,
        settled_by="correctness per above; section 19.6 fixes both axes and notes that three "
        "evidence bands give three points, which is a curve only by courtesy",
    ),
    MetricRow(
        layer="Investigation",
        metric="Calibrated confidence",
        manifest=None,
        key=None,
        denominator="14 episodes",
        status=Status.DEFERRED,
        settled_by="more episodes and an outcome definition; at 14, a per-bin interval is about 25 "
        "points wide, so section 19.4 reports evidence bands and no outcome rates",
    ),
    MetricRow(
        layer="Investigation",
        metric="Prose-quality judge scores",
        manifest=None,
        key=None,
        denominator="would need a model and the author's own scores",
        status=Status.DEFERRED,
        settled_by="a configured model provider key; the rubric is fixed in section 19.8, and "
        "prose quality is the one thing here the author can judge unaided",
    ),
)
