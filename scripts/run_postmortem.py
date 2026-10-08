"""The post-mortem, the lessons register and the correction store, per protocol section 20.

    python scripts/run_postmortem.py data/cache/ddr_xml

Calls no model. Exit status is the gate: non-zero when any section 20.6 pass mark fails.

A day rate is not built in and no currency figure appears unless `--day-rate-usd` is supplied.
Section 20.3 is explicit about why: a rig day rate is a commercial negotiation this project has no
access to, and an illustration that circulates as a finding is the failure mode.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from volve_ops.extraction.labels import read_label_file
from volve_ops.extraction.sampling import HOLD_OUT_WELLS
from volve_ops.extraction.store import EventStore
from volve_ops.postmortem import (
    POSTMORTEM_VERSION,
    corrections,
    gates,
    recorded_time,
    register,
)


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
    # "not reported", not "not computed": section 20.1 was narrowed because the hold-out wells *are*
    # reconciled, over all eleven, and the gate below says `examined 11`. The earlier wording here
    # repeated on every run the sentence the protocol had retracted.
    print(
        f"development   {len(development)} wells; "
        f"hold-out {len(held_out)} reconciled, not reported"
    )
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

    # ------------------------------------------------------------------ the register
    events = list(EventStore(args.store).read(args.version))
    rows = read_label_file(args.labels) if args.labels.exists() else []
    labelled = {str(r["event_id"]) for r in rows}
    miscoded = {str(r["event_id"]) for r in rows if r.get("source_coding_looks_wrong")}
    built = register.build(
        events,
        wells=development,
        labelled_event_ids=labelled,
        miscoded_event_ids=miscoded,
    )
    print(
        f"\nlessons register: {len(built.patterns)} recurring patterns of "
        f"{len(built.patterns) + built.excluded_patterns}, covering "
        f"{built.recurring_hours:,.1f} h of {built.corpus_hours:,.1f} = {built.coverage:.1%}"
    )
    print(
        f"  below the section 20.4 thresholds ({register.MIN_WELLS} wells, "
        f"{register.MIN_HOURS:.0f} h): {built.excluded_patterns} patterns, "
        f"{built.excluded_hours:,.1f} h"
    )
    print(
        f"\n{'subcategory':<26} {'detail state':<20} {'wells':>6} {'events':>7} "
        f"{'hours':>8} {'labelled':>9} {'mis-filed':>10}"
    )
    for pattern in built.patterns:
        print(
            f"  {pattern.subcategory[:24]:<24} {pattern.detail_state[:18]:<18} "
            f"{len(pattern.wells):>6} {pattern.events:>7} {pattern.total_hours:>8,.0f} "
            f"{pattern.labelled_fraction:>8.0%} {pattern.miscoded_fraction:>9.0%}"
        )

    # What the thresholds exclude, published rather than summarised. Review found the register
    # silently dropping sidetrack, lost circulation, well control and casing, which are the shapes
    # an operations reader opens a register to find.
    print("\nlargest patterns the section 20.4 thresholds exclude:")
    print(f"{'subcategory':<26} {'detail state':<20} {'wells':>6} {'events':>7} {'hours':>8}")
    for pattern in built.excluded[:10]:
        print(
            f"  {pattern.subcategory[:24]:<24} {pattern.detail_state[:18]:<18} "
            f"{len(pattern.wells):>6} {pattern.events:>7} {pattern.total_hours:>8,.0f}"
        )
    print(
        "  a single-well event cannot appear in the register however expensive, because the "
        "three-well bar is what excludes it"
    )

    labelled_in_register = sum(p.labelled_events for p in built.patterns)
    events_in_register = sum(p.events for p in built.patterns)
    print(
        f"\nevents in recurring patterns carrying a cause label: {labelled_in_register} of "
        f"{events_in_register} = {labelled_in_register / events_in_register:.1%}"
        if events_in_register
        else "\nno recurring pattern, so no labelled fraction"
    )

    amount, assumption = register.cost_equivalent(built.recurring_hours, args.day_rate_usd)
    if amount is None:
        print("no currency figure: no day rate supplied, and none is built in (section 20.3)")
    else:
        print(f"estimated rig-time cost equivalent: {amount:,.0f} USD, {assumption}")

    # ------------------------------------------------------------------ the correction store
    store = corrections.CorrectionStore(args.corrections)
    store_versions = store.versions()
    stored = [c for version in store_versions for c in store.read(version)]
    print(
        f"\ncorrection store: {len(store_versions)} version(s) {store_versions}, "
        f"{len(stored)} correction(s)"
    )

    # ------------------------------------------------------------------ the gates
    store_hours: dict[str, float] = {}
    store_counts: dict[str, int] = {}
    for event in events:
        store_hours[event.well] = store_hours.get(event.well, 0.0) + event.duration_hours
        store_counts[event.well] = store_counts.get(event.well, 0) + 1

    provisional: dict[str, Any] = {
        "day_rate_usd": args.day_rate_usd,
        "cost_equivalent_usd": None if amount is None else round(amount, 2),
        "cost_assumption": assumption or None,
    }
    outcomes = [
        gates.corpus_is_not_empty(walked, events, built),
        gates.categories_reconcile(walked, store_hours, store_counts),
        gates.citations_resolve(built, events),
        gates.hold_out_is_contained(built, scope, stored),
        gates.currency_is_disclosed(provisional),
        gates.refusal_is_demonstrated(store),
        # Passed the register that is about to be published, and the same label and miscoding sets
        # it was built from. The first version was handed neither, so it reproduced an artifact
        # nobody was publishing.
        gates.register_is_reproducible(
            built,
            events,
            wells=development,
            labelled_event_ids=sorted(labelled),
            miscoded_event_ids=sorted(miscoded),
        ),
    ]
    print("\nsection 20.6 pass marks:")
    for outcome in outcomes:
        print(
            f"  {'PASS' if outcome.passed else 'FAIL'}  {outcome.name} "
            f"(examined {outcome.examined})"
        )
        for line in outcome.detail[:4]:
            print(f"        ! {line}")
    vacuous = [o.name for o in outcomes if o.vacuous]
    if vacuous:
        print(f"  gates that examined nothing, and so demonstrate nothing: {vacuous}")

    marks = {o.name: o.passed for o in outcomes}

    payload: dict[str, Any] = {
        **provisional,
        "protocol_version": "v11",
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
        # The headline figures, in the manifest rather than computed in a document. Review found
        # them quoted in bold in the results and the README while being derivable from neither.
        "events_in_recurring_patterns": built.events_in_patterns,
        "labelled_events_in_recurring_patterns": built.labelled_events_in_patterns,
        "labelled_fraction_of_recurring_patterns": round(built.labelled_fraction_of_patterns, 4),
        "largest_excluded_pattern_hours": (
            round(built.excluded[0].total_hours, 2) if built.excluded else 0.0
        ),
        "patterns": [p.model_dump(mode="json") for p in built.patterns],
        "excluded_pattern_detail": [p.model_dump(mode="json") for p in built.excluded],
        "correction_store_versions": store_versions,
        "corrections": len(stored),
        "gates_that_examined_nothing": vacuous,
        "pass_marks": marks,
        "all_pass": all(marks.values()),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nrun manifest written to {args.manifest}")
    return 0 if all(marks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
