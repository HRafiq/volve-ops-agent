"""The evaluation harness of protocol section 19, behind the development results table.

    python scripts/run_evaluation.py "data/cache/Volve production data.xlsx" data/cache/ddr_xml

It calls no model, and section 19.10 requires that the free workflow cannot: everything here runs on
the deterministic layers and on the manifests the other scripts wrote.

Exit status is the gate. Non-zero when any section 19 pass mark fails, so the free CI workflow fails
on a leakage finding or an uncovered figure rather than printing one and passing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from volve_ops import INGEST_VERSION
from volve_ops.domain.activity import activity_dates_by_well
from volve_ops.domain.episodes import sweep_well
from volve_ops.domain.expectation import NaiveMedian28
from volve_ops.domain.production_service import load_volve_production
from volve_ops.domain.regimes import stable_reference_windows
from volve_ops.domain.splits import derive_split, development_only
from volve_ops.domain.well_naming import well_of
from volve_ops.evaluation import HARNESS_VERSION, evidence, leakage, safety, table, trajectory
from volve_ops.evaluation.rows import ROWS
from volve_ops.evaluation.versions import (
    ABSENT,
    VersionFreeze,
    current_commit,
    describe_model_roles,
    missing_fields,
)
from volve_ops.extraction import EXTRACTOR_VERSION
from volve_ops.extraction.labels import read_label_file
from volve_ops.extraction.store import EventStore
from volve_ops.investigation import INVESTIGATOR_VERSION
from volve_ops.investigation.diagnostics import build_bundle
from volve_ops.investigation.schemas import Finding
from volve_ops.investigation.trace import Trace

#: Semantic roles from plan section 9.3. None is bound to a model in this project.
MODEL_ROLES: dict[str, str | None] = {
    "EXTRACTION": None,
    "INVESTIGATION": None,
    "JUDGE": None,
    "EMBEDDING": None,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("--store", type=Path, default=Path("data/cache/npt_store"))
    parser.add_argument("--version", default="extractor-v0")
    parser.add_argument("--labels", type=Path, default=Path("labels"))
    parser.add_argument("--runs", type=Path, default=Path("data/cache"))
    parser.add_argument("--investigations", type=Path, default=Path("data/cache/investigations"))
    parser.add_argument("--out", type=Path, default=Path("data/cache/evaluation_run.json"))
    parser.add_argument(
        "--table", type=Path, default=None, help="write the rendered table to this file"
    )
    args = parser.parse_args(argv)

    # ------------------------------------------------------------------ version freeze
    manifests = table.load_manifests(args.runs)
    dataset = manifests.get("expectation", {}).get("dataset_version", {})
    workbook_hash = str(dataset.get("workbook", {}).get("sha256", ABSENT))[:16] or ABSENT
    label_file = args.labels / "development_pass1.jsonl"
    label_rows = read_label_file(label_file) if label_file.exists() else []
    provenance = sorted({str(r.get("label_source")) for r in label_rows}) or [ABSENT]

    freeze = VersionFreeze(
        dataset_version=f"workbook sha256 {workbook_hash}, "
        f"{dataset.get('drilling_reports', {}).get('files', ABSENT)} reports",
        label_set_version=f"{label_file.name} n={len(label_rows)} "
        f"provenance={'+'.join(provenance)}",
        parser_version=INGEST_VERSION,
        extractor_version=EXTRACTOR_VERSION,
        investigator_version=INVESTIGATOR_VERSION,
        retrieval_index_version=f"bm25 over "
        f"{manifests.get('extraction', {}).get('indexed_chunks', ABSENT)} chunks",
        correction_store_version=ABSENT,
        model_roles=describe_model_roles(MODEL_ROLES),
        commit=current_commit(),
    )
    print(f"harness {HARNESS_VERSION}; manifest hash {freeze.manifest_hash}")
    for field in sorted(freeze.model_dump()):
        print(f"  {field:<24} {getattr(freeze, field)}")
    # Both of these were tautologies in the first version, and review was right about both.
    #
    # `missing_fields` was applied to a freshly validated `VersionFreeze`, whose validator already
    # refuses a blank field, so it could only ever return nothing. It is meant for a manifest read
    # back from disk, which is where a field can actually be absent, and that is where it runs now.
    #
    # The reproducibility mark compared `freeze.manifest_hash` with `freeze.model_copy()`'s, an
    # object against its own copy. Reproduction means across runs, so this compares against the hash
    # the previous run persisted, and only when that run was on the same commit: the commit is one
    # of the nine fields, so the hash is commit-dependent by design and a mismatch across commits
    # is expected rather than a failure.
    previous: dict[str, Any] = {}
    if args.out.exists():
        previous = json.loads(args.out.read_text(encoding="utf-8"))
    blank = missing_fields(previous.get("version_freeze", {})) if previous else ()
    same_commit = previous.get("version_freeze", {}).get("commit") == freeze.commit
    reproduced = (
        previous.get("manifest_hash") == freeze.manifest_hash if previous and same_commit else True
    )
    if not previous:
        print("  no previous run to compare against; the reproducibility mark has nothing to test")
    elif not same_commit:
        print(
            f"  previous run was commit {previous.get('version_freeze', {}).get('commit')}; "
            "the hash includes the commit, so it is not expected to match"
        )

    # ------------------------------------------------------------------ leakage audit
    history = load_volve_production(args.workbook)
    split = derive_split(history.days)
    # Read from the manifests, never recomputed here. Review showed that a harness deriving the
    # fitted day set with the same filter it then audits cannot catch a leak: it tests the negation
    # of its own comprehension. The scripts record the dates they used; this reads them.
    recorded_fits: dict[str, list[str]] = {}
    for name, key in (("expectation", "fitted_day_dates"), ("investigation", "bundle_day_dates")):
        for well, dates in (manifests.get(name, {}).get(key, {}) or {}).items():
            recorded_fits.setdefault(str(well), []).extend(str(d) for d in dates)

    # The population every investigation read, which is wider than the wells that produced a
    # finding: the offset comparison in the diagnostic bundle sees all of them.
    bundle_population = sorted(
        set(manifests.get("investigation", {}).get("development_wells", []))
        | set(manifests.get("investigation", {}).get("bundle_day_dates", {}))
    )

    events = {e.event_id: e for e in EventStore(args.store).read(args.version)}
    labelled_dates = {
        str(r["event_id"]): events[str(r["event_id"])].report_date
        for r in label_rows
        if str(r["event_id"]) in events
    }
    labelled_wells = {
        events[str(r["event_id"])].well for r in label_rows if str(r["event_id"]) in events
    }

    findings = [
        Finding.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(args.investigations.glob("*.finding.json"))
    ]
    traces = [Trace.read(p) for p in sorted(args.investigations.glob("*.trace.json"))]

    audit = leakage.audit(
        fitted_wells=sorted(recorded_fits),
        fitted_days=recorded_fits,
        split=split,
        labelled_report_dates=labelled_dates,
        labelled_wells=sorted(labelled_wells),
        investigated_wells=bundle_population or sorted({f.well for f in findings}),
        label_dir=args.labels if args.labels.exists() else None,
    )
    print(f"\nleakage audit: {'clean' if audit.clean else 'FINDINGS'}")
    for name, count in sorted(audit.examined.items()):
        print(f"  {name:<40} examined {count}")
    for leak in audit.findings:
        print(f"  ! {leak.check}: {leak.detail}")
    if audit.vacuous_checks:
        print(f"  checks that examined nothing: {list(audit.vacuous_checks)}")

    # ------------------------------------------------------------------ safety and trajectory
    safety_report = safety.assess(findings)
    print(
        f"\nfalse root-cause claims, mechanical half: {len(safety_report.incidents)} "
        f"over {safety_report.documented_claims} documented claims in "
        f"{safety_report.findings_examined} findings"
    )
    for incident in safety_report.incidents:
        print(f"  ! {incident.kind}: {incident.finding_id}: {incident.detail}")
    if not safety_report.examined_anything:
        print("  no finding claims a documented root cause, so this gate examined nothing")

    path_report = trajectory.assess(traces, findings, model_called=freeze.calls_a_model)
    print(
        f"\ntrajectory: {path_report.investigations} runs, steps "
        f"{path_report.steps_min}-{path_report.steps_max}, mean {path_report.steps_mean:.1f}; "
        f"{path_report.tokens} tokens, ${path_report.cost_usd:.2f}"
    )
    print(f"  retrieval passes per run: {path_report.retrieval_passes}")
    print(f"  retrieval queries in total: {sum(path_report.retrieval_passes_total)}")
    print(f"  stop conditions: {path_report.stop_conditions}")
    print(f"  repeated identical calls: {len(path_report.repeated_calls)}")
    if path_report.stability_is_determinism:
        print("  verdict stability is 1.0 by construction: no model is called, so this is")
        print("  determinism rather than reliability, per section 19.7")

    # ------------------------------------------------------------------ evidence bands
    #
    # The population is taken from what the investigation recorded rather than rebuilt from a
    # filter of this script's own. Review found the two differing by one well, which changed the
    # offset comparison inside every rebuilt bundle; the figures happened to coincide, which is luck
    # and not a property worth relying on.
    usable = {well: development_only(history.for_well(well), split) for well in bundle_population}
    activity = activity_dates_by_well(args.report_dir)
    windows = {
        well: stable_reference_windows(days, activity_dates=activity.get(well_of(well), set()))
        for well, days in usable.items()
    }
    episodes = []
    for well in sorted(usable):
        episodes.extend(sweep_well(well, usable[well], windows[well], NaiveMedian28()))
    by_key = {(f.well, f.episode_onset): f for f in findings}

    bands: dict[str, int] = {}
    scored: list[dict[str, Any]] = []
    for episode in episodes:
        found = by_key.get((episode.well, episode.onset.isoformat()))
        if found is None:
            continue
        bundle = build_bundle(episode.well, episode.onset, episode.offset, usable)
        score = evidence.score_finding(found, bundle)
        bands[score.band.value] = bands.get(score.band.value, 0) + 1
        scored.append(
            {
                "well": episode.well,
                "onset": episode.onset.isoformat(),
                "score": round(score.score, 4),
                "band": score.band.value,
                "verdict": found.verdict.value,
                "stop_reason": found.stop_reason.value,
                "citations": sum(len(h.supporting) for h in found.hypotheses),
                "features": {k: round(v, 4) for k, v in score.features.items()},
            }
        )
    print(f"\nevidence bands over {len(scored)} findings: {bands}")
    print("  band against verdict and citations, no outcome rates, per section 19.4:")
    for row in scored:
        print(
            f"    {row['well']} {row['onset']}  {row['band']:<9} {row['score']:.2f}  "
            f"{row['verdict']:<32} citations {row['citations']}"
        )

    # ------------------------------------------------------------------ the table
    # Rows the harness computes rather than reads. Without these the leakage row rendered as
    # "not produced" next to a gate that had just run.
    computed = {
        "Leakage audit, five checks of section 19.2": audit.clean,
        "False root-cause claims, mechanical half": len(safety_report.incidents),
    }
    filled = table.fill(ROWS, manifests, computed)
    uncovered = table.uncovered(ROWS, manifests)
    rendered = table.as_markdown(filled)
    print(f"\nresults table: {len(filled)} rows; uncovered manifest figures: {len(uncovered)}")
    for key in uncovered:
        print(f"  ! no row covers {key}")
    if args.table is not None:
        args.table.parent.mkdir(parents=True, exist_ok=True)
        args.table.write_text(rendered, encoding="utf-8")
        print(f"  table written to {args.table}")

    # ------------------------------------------------------------------ pass marks
    marks = {
        "19.1 every version field present in the persisted manifest": not blank,
        "19.1 manifest hash reproduces on the same commit": reproduced,
        "19.2 leakage audit clean": audit.clean,
        "19.3 every manifest figure has a table row": not uncovered,
        "19.5 no mechanical false root-cause claim": safety_report.passed,
        "19.7 no repeated identical tool call": path_report.passed,
    }
    print("\nsection 19 pass marks:")
    for name, passed in marks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")

    payload: dict[str, Any] = {
        "protocol_version": "v8",
        "harness_version": HARNESS_VERSION,
        "version_freeze": freeze.model_dump(),
        "manifest_hash": freeze.manifest_hash,
        "leakage": audit.model_dump(mode="json"),
        "safety": safety_report.model_dump(mode="json"),
        "trajectory": path_report.model_dump(mode="json"),
        "evidence_bands": bands,
        "evidence_scores": scored,
        "table_rows": len(filled),
        "uncovered_figures": uncovered,
        "pass_marks": marks,
        "all_pass": all(marks.values()),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nrun manifest written to {args.out}")
    return 0 if all(marks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
