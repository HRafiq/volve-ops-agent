"""The post-mortem, the lessons register and the correction store, per protocol section 20.

    python scripts/run_postmortem.py data/cache/ddr_xml

Calls no model. Exit status is the gate: non-zero when any section 20.6 pass mark fails.

A day rate is not built in and no currency figure appears unless `--day-rate-usd` is supplied.
Section
20.3 is explicit about why: a rig day rate is a commercial negotiation this project has no access
to,
and an illustration that circulates as a finding is the failure mode.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from volve_ops.extraction.labels import read_label_file
from volve_ops.extraction.sampling import HOLD_OUT_WELLS
from volve_ops.extraction.store import EventStore
from volve_ops.postmortem import POSTMORTEM_VERSION, corrections, recorded_time, register

#: Section 20.2's reconciliation tolerance. Floating point and nothing else.
RECONCILE_TOLERANCE_HOURS = 0.01


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("--store", type=Path, default=Path("data/cache/npt_store"))
    parser.add_argument("--version", default="extractor-v0")
    parser.add_argument("--labels", type=Path, default=Path("labels/development_pass1.jsonl"))
    parser.add_argument("--corrections", type=Path, default=Path("data/cache/corrections"))
    parser.add_argument("--manifest", type=Path, default=Path("data/cache/postmortem_run.json"))
    parser.add_argument(
        "--day-rate-usd",
        type=float,
        default=None,
        help="a stated assumption; omitted means no currency figure is computed at all",
    )
    args = parser.parse_args(argv)

    # ------------------------------------------------------------------ recorded time
    walked = recorded_time.walk(args.report_dir)
    development = sorted(w.well for w in walked.wells if w.well not in HOLD_OUT_WELLS)
    held_out = sorted(w.well for w in walked.wells if w.well in HOLD_OUT_WELLS)
    scope = walked.only(development)

    print(f"corpus        {walked.reports} reports, {walked.blocks} activity blocks")
    print(f"              {walked.untimed_blocks} untimed")
    print(f"development   {len(development)} wells; hold-out {len(held_out)} not computed")
    print(
        f"\nrecorded time over the whole corpus: NPT {walked.npt_hours:,.0f} h, "
        f"non-NPT {walked.non_npt_recorded_hours:,.0f} h, "
        f"unclassified gaps {walked.unclassified_gap_hours:,.0f} h, "
        f"concurrent overlap {walked.concurrent_overlap_hours:,.1f} h"
    )
    excluded_share = 1.0 - scope.npt_hours / walked.npt_hours if walked.npt_hours > 0 else 0.0
    print(
        f"development only: NPT {scope.npt_hours:,.0f} h of {walked.npt_hours:,.0f}, "
        f"so {excluded_share:.1%} of the corpus's non-productive time is held out and not reported"
    )

    print(f"\n{'well':<14} {'reports':>8} {'NPT h':>9} {'non-NPT h':>10} {'NPT share':>10}")
    for well in scope.wells:
        print(
            f"  {well.well:<12} {well.reports:>8} {well.npt_hours:>9,.0f} "
            f"{well.non_npt_recorded_hours:>10,.0f} {well.npt_share:>9.1%}"
        )

    # ------------------------------------------------------------------ reconciliation, gating
    events = list(EventStore(args.store).read(args.version))
    store_npt: dict[str, float] = {}
    for event in events:
        store_npt[event.well] = store_npt.get(event.well, 0.0) + event.duration_hours

    mismatches: list[str] = []
    for well in walked.wells:
        reconciled = abs(well.npt_hours + well.non_npt_recorded_hours - well.block_duration_hours)
        if reconciled > RECONCILE_TOLERANCE_HOURS:
            mismatches.append(f"{well.well}: categories do not sum to block duration")
        # The section 20.8 spot-verification: this walk against the extractor's own store.
        from_store = store_npt.get(well.well, 0.0)
        if abs(well.npt_hours - from_store) > RECONCILE_TOLERANCE_HOURS:
            mismatches.append(
                f"{well.well}: this walk says {well.npt_hours:,.2f} NPT hours, the event store "
                f"says {from_store:,.2f}"
            )
    print(f"\nreconciliation: {len(mismatches)} mismatch(es) across {len(walked.wells)} wells")
    for line in mismatches[:5]:
        print(f"  ! {line}")

    # ------------------------------------------------------------------ the register
    labelled = (
        {str(r["event_id"]) for r in read_label_file(args.labels)}
        if args.labels.exists()
        else set()
    )
    built = register.build(events, wells=development, labelled_event_ids=labelled)
    print(
        f"\nlessons register: {len(built.patterns)} recurring patterns of "
        f"{len(built.patterns) + built.excluded_patterns}, covering "
        f"{built.recurring_hours:,.0f} h of {built.corpus_hours:,.0f} = {built.coverage:.1%}"
    )
    print(
        f"  below the section 20.4 thresholds ({register.MIN_WELLS} wells, "
        f"{register.MIN_HOURS:.0f} h): {built.excluded_patterns} patterns, "
        f"{built.excluded_hours:,.0f} h"
    )
    print(
        f"\n{'subcategory':<26} {'detail state':<20} {'wells':>6} {'events':>7} "
        f"{'hours':>8} {'labelled':>9}"
    )
    for pattern in built.patterns:
        print(
            f"  {pattern.subcategory[:24]:<24} {pattern.detail_state[:18]:<18} "
            f"{len(pattern.wells):>6} {pattern.events:>7} {pattern.total_hours:>8,.0f} "
            f"{pattern.labelled_fraction:>8.0%}"
        )

    top = built.patterns[0] if built.patterns else None
    if top is not None:
        print(f"\nlargest pattern, {top.subcategory} / {top.detail_state}:")
        print(f"  {top.events} events on {len(top.wells)} wells, {top.total_hours:,.0f} h")
        print(f"  {top.first_seen} to {top.last_seen}")
        print(f"  cited: {top.representative.locator}")
        print(f"  span:  {top.representative.span[:110]!r}")

    amount, assumption = register.cost_equivalent(built.recurring_hours, args.day_rate_usd)
    if amount is None:
        print("\nno currency figure: no day rate supplied, and none is built in (section 20.3)")
    else:
        print(f"\nestimated rig-time cost equivalent: {amount:,.0f} USD, {assumption}")

    # ------------------------------------------------------------------ citations, gating
    by_id = {e.event_id: e for e in events}
    bad_citations: list[str] = []
    for pattern in built.patterns:
        cited = by_id.get(pattern.representative.event_id)
        if cited is None:
            bad_citations.append(f"{pattern.representative.event_id} is not in the store")
        elif pattern.representative.span not in cited.comment:
            bad_citations.append(f"{pattern.representative.event_id}: span is not verbatim")
        elif cited.source_document != pattern.representative.source_document:
            bad_citations.append(f"{pattern.representative.event_id}: wrong source document")
    print(f"\ncitations: {len(built.patterns) - len(bad_citations)}/{len(built.patterns)} resolve")
    for line in bad_citations[:5]:
        print(f"  ! {line}")

    # ------------------------------------------------------------------ hold-out containment
    leaked = sorted(
        {w for w in built.wells if corrections.is_hold_out(w)}
        | {w.well for w in scope.wells if corrections.is_hold_out(w.well)}
    )
    store = corrections.CorrectionStore(args.corrections)
    store_versions = store.versions()
    stored = [c for version in store_versions for c in store.read(version)]
    leaked_corrections = sorted({c.well for c in stored if corrections.is_hold_out(c.well)})
    print(
        f"\nhold-out containment: {len(leaked)} hold-out well(s) in the post-mortem, "
        f"{len(leaked_corrections)} in the correction store"
    )
    print(
        f"  correction store: {len(store_versions)} version(s) {store_versions}, "
        f"{len(stored)} correction(s)"
    )

    # The refusal is demonstrated rather than asserted: section 20.8 asks for it.
    refuses = False
    probe = next((e for e in events if corrections.is_hold_out(e.well)), None)
    if probe is not None:
        candidate = corrections.propose(
            probe,
            corrections.CorrectionField.EQUIPMENT,
            "probe",
            corrected_by="harness",
            note="section 20.8 probe; never written",
        )
        try:
            store.write("probe-never-written", [candidate])
        except corrections.HoldOutCorrectionRefused:
            refuses = True
        print(
            f"  write-time refusal of a hold-out correction: "
            f"{'demonstrated' if refuses else 'NOT DEMONSTRATED'} on {probe.well}"
        )

    marks = {
        "20.2 categories reconcile and the store agrees": not mismatches,
        "20.6 every citation resolves": not bad_citations,
        "20.6 no hold-out well in the post-mortem or the store": not leaked
        and not leaked_corrections,
        "20.3 no currency figure without its assumption": amount is None or bool(assumption),
        "20.5 a hold-out correction is refused at write time": refuses,
    }
    print("\nsection 20.6 pass marks:")
    for name, passed in marks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")

    payload: dict[str, Any] = {
        "protocol_version": "v9",
        "postmortem_version": POSTMORTEM_VERSION,
        "reports": walked.reports,
        "activity_blocks": walked.blocks,
        "untimed_blocks": walked.untimed_blocks,
        "development_wells": development,
        "hold_out_wells_excluded": held_out,
        "corpus_npt_hours": round(walked.npt_hours, 2),
        "corpus_non_npt_recorded_hours": round(walked.non_npt_recorded_hours, 2),
        "corpus_unclassified_gap_hours": round(walked.unclassified_gap_hours, 2),
        "corpus_concurrent_overlap_hours": round(walked.concurrent_overlap_hours, 2),
        "development_npt_hours": round(scope.npt_hours, 2),
        "development_non_npt_recorded_hours": round(scope.non_npt_recorded_hours, 2),
        "held_out_npt_share": round(excluded_share, 4),
        "per_well": [w.model_dump(mode="json") for w in scope.wells],
        "recurring_patterns": len(built.patterns),
        "excluded_patterns": built.excluded_patterns,
        "excluded_hours": round(built.excluded_hours, 2),
        "register_hours": round(built.recurring_hours, 2),
        "register_coverage": round(built.coverage, 4),
        "patterns": [p.model_dump(mode="json") for p in built.patterns],
        "day_rate_usd": args.day_rate_usd,
        "cost_equivalent_usd": None if amount is None else round(amount, 2),
        "cost_assumption": assumption or None,
        "correction_store_versions": store_versions,
        "corrections": len(stored),
        "hold_out_refusal_demonstrated": refuses,
        "pass_marks": marks,
        "all_pass": all(marks.values()),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nrun manifest written to {args.manifest}")
    return 0 if all(marks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
