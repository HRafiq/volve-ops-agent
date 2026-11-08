"""The ablations of protocol section 22.7, and the numbers the health tab reports.

Each ablation removes one capability, re-runs on development data only, and reports what moved.
The hold-out is not touched; section 19.2 checks that.

An ablation that moves nothing is reported as moving nothing. That is the point of running them:
a capability whose removal changes no verdict is a capability this dataset cannot speak to, and
saying so is worth more than leaving the row out and implying it was never asked.

    python scripts/run_ablations.py data/cache/Volve\\ production\\ data.xlsx data/cache/ddr_xml

Writes `data/cache/ablation_run.json`, which the System Health workspace renders and which the
section 22 gate reads. Every figure there is produced here; section 21.1 does not let a serving
layer derive one.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from volve_ops.console.assemble import CONSOLE_PROTOCOL_VERSION
from volve_ops.domain.activity import activity_dates_by_well
from volve_ops.domain.backtest import HORIZONS, run_backtest
from volve_ops.domain.day_class import DayClass
from volve_ops.domain.episodes import sweep_well
from volve_ops.domain.expectation import CANDIDATE_MODELS, NaiveMedian28
from volve_ops.domain.production_service import load_volve_production
from volve_ops.domain.regimes import stable_reference_windows
from volve_ops.domain.splits import derive_split, development_only
from volve_ops.domain.well_naming import well_of
from volve_ops.evaluation.evidence import HIGH_BAND, MODERATE_BAND, score_finding
from volve_ops.extraction.store import EventStore
from volve_ops.investigation.controller import EVIDENCE_WINDOW_DAYS, investigate
from volve_ops.investigation.diagnostics import build_bundle
from volve_ops.investigation.validator import CitableDocument
from volve_ops.provenance.facts import FactLedger
from volve_ops.retrieval.index import BM25Index, chunks_from_events

#: Cost denominated in model calls is not applicable here and is declared rather than counted.
#: Section 22.7: no module calls a model, so a token curve would be a decorative zero.
COST_NOT_APPLICABLE: Final[dict[str, str]] = {
    "tokens_per_investigation": (
        "No module in this system calls a language model, so no tokens are consumed by an "
        "investigation. A figure here would be zero for every run and would read as a measured "
        "efficiency rather than an absent component."
    ),
    "model_calls_per_investigation": (
        "The controller's stages are deterministic and the judgement role is rule-based, so an "
        "investigation makes no model calls at all. Section 18.1 is what fixes that, and the "
        "trace records actions rather than a model's intermediate text."
    ),
    "usd_per_investigation": (
        "No metered third-party service is called, so there is no spend to attribute. What an "
        "investigation costs here is compute time, which is measured and reported above."
    ),
}


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def documents_in_window(episode: Any, events: Sequence[Any]) -> list[Any]:
    """Events whose report date falls inside the episode's evidence window, for its own well.

    The controller's window and well normalisation, so this counts what retrieval could reach
    rather than what it chose to cite.
    """
    low = episode.onset - dt.timedelta(days=EVIDENCE_WINDOW_DAYS)
    high = episode.offset + dt.timedelta(days=EVIDENCE_WINDOW_DAYS)
    return [
        event
        for event in events
        if well_of(event.well) == well_of(episode.well) and low <= event.report_date <= high
    ]


def _episodes_opened_by(
    model: Any, usable: Mapping[str, Sequence[Any]], windows: Mapping[str, Any]
) -> int:
    return sum(len(sweep_well(w, usable[w], windows[w], model)) for w in sorted(usable))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("--store", type=Path, default=Path("data/cache/npt_store"))
    parser.add_argument("--version", default="extractor-v0")
    parser.add_argument("--out", type=Path, default=Path("data/cache/ablation_run.json"))
    args = parser.parse_args(argv)

    history = load_volve_production(args.workbook)
    split = derive_split(history.days)
    producers = sorted(
        {d.day.well for d in history.days if d.day_class is DayClass.VALID_PRODUCING}
    )
    usable = {
        well: days
        for well, days in ((w, development_only(history.for_well(w), split)) for w in producers)
        if any(d.day_class is DayClass.VALID_PRODUCING for d in days)
    }
    activity = activity_dates_by_well(args.report_dir)
    windows = {
        well: stable_reference_windows(days, activity_dates=activity.get(well_of(well), set()))
        for well, days in usable.items()
    }

    # --- ablation 1: expectation (F1) ---------------------------------------------------------
    # A bad expectation manufactures investigations, so the measurement is how many episodes each
    # model opens, beside its accuracy.
    print("ablation 1: expectation")
    results = run_backtest(usable, windows)
    expectation_rows = []
    # CANDIDATE_MODELS already contains the two baselines, so naming them again listed each
    # twice and would have put a duplicate row on the health tab.
    for model in CANDIDATE_MODELS:
        name = model.name
        opened = _episodes_opened_by(model, usable, windows)
        wape = results[name].pooled_wape(HORIZONS[0]) if name in results else None
        expectation_rows.append(
            {"model": name, "episodes_opened": opened, f"wape_h{HORIZONS[0]}": wape}
        )
        print(f"  {name:<24} episodes {opened:>3}  wape {wape}")

    # --- ablation 2: retrieval (F5) -----------------------------------------------------------
    # ADR 0008: most episodes have no in-window document at all, so this runs on the minority
    # that do. The population size is reported with the result because it is the result's most
    # important qualifier: an ablation over one episode measures one episode.
    print("\nablation 2: retrieval")
    events = list(EventStore(args.store).read(args.version))
    index = BM25Index(chunks_from_events(events))
    documents = {
        event.event_id: CitableDocument(
            event_id=event.event_id,
            source_document=event.source_document,
            well=event.well,
            report_date=event.report_date,
            text=event.comment,
        )
        for event in events
    }
    empty_index = BM25Index([])

    episodes = [
        e for w in sorted(usable) for e in sweep_well(w, usable[w], windows[w], NaiveMedian28())
    ]
    # Every episode swept, with how many documents its window holds, including the ones that open
    # no arm. Published so mark 9 can reconcile the population against the whole sweep rather than
    # against the survivors: the figure amendment 12 records as wrong in four places was wrong
    # precisely because the survivors were all that anything could see.
    episode_document_counts = [
        {
            "well": e.well,
            "onset": e.onset.isoformat(),
            "documents_in_window": len(documents_in_window(e, events)),
        }
        for e in episodes
    ]
    retrieval_rows = []
    for episode in episodes:
        bundle = build_bundle(episode.well, episode.onset, episode.offset, usable)
        with_docs = investigate(episode, bundle, index, documents, FactLedger())
        cited = sum(
            1
            for h in (with_docs.finding.hypotheses if with_docs.finding else ())
            for r in (*h.supporting, *h.contradicting)
            if r.span is not None
        )
        # The gate is **documents available in the window**, not spans the controller happened to
        # cite. The first version skipped on `cited == 0` with a comment saying the episode had no
        # document to take away, which is a different claim: an episode can have in-window
        # documents that retrieval found and could not cite. One of the two episodes that have
        # documents cites none, so it was dropped, and the surviving count was published under the
        # label "episodes with any in-window document" in the manifest, on the health tab, in the
        # results document and in the README. All four said one. It is two.
        #
        # Section 22.4 mark 9 is explicit that an ablation which moves nothing is reported as
        # moving nothing. Dropping it is the one thing that mark forbids.
        in_window = documents_in_window(episode, events)
        if not in_window:
            continue
        without = investigate(episode, bundle, empty_index, {}, FactLedger())
        a, b = with_docs.finding, without.finding
        band_with = score_finding(a, bundle).band if a else None
        band_without = score_finding(b, bundle).band if b else None
        row = {
            "well": episode.well,
            "onset": episode.onset.isoformat(),
            "spans_cited": cited,
            "documents_in_window": len(in_window),
            "verdict_with": str(a.verdict) if a else None,
            "verdict_without": str(b.verdict) if b else None,
            "evidence_band_with": str(band_with) if band_with else None,
            "evidence_band_without": str(band_without) if band_without else None,
            "highest_level_with": str(a.highest_level) if a else None,
            "highest_level_without": str(b.highest_level) if b else None,
        }
        # Three dimensions, each reported separately. A first version printed the verdict alone
        # and the run looked like a null result; the causal level was what moved, which is the
        # one thing the retrieval stage exists to lift.
        row["verdict_changed"] = row["verdict_with"] != row["verdict_without"]
        row["band_changed"] = row["evidence_band_with"] != row["evidence_band_without"]
        row["level_changed"] = row["highest_level_with"] != row["highest_level_without"]
        retrieval_rows.append(row)
        moved = [
            k[: -len("_changed")]
            for k in ("verdict_changed", "band_changed", "level_changed")
            if row[k]
        ]
        print(
            f"  {episode.well} {episode.onset}: {cited} span(s); "
            f"moved: {', '.join(moved) if moved else 'nothing'}"
        )
        print(
            f"      verdict {row['verdict_with']} -> {row['verdict_without']}\n"
            f"      band    {row['evidence_band_with']} -> {row['evidence_band_without']}\n"
            f"      level   {row['highest_level_with']} -> {row['highest_level_without']}"
        )
    moved_nothing = [
        r
        for r in retrieval_rows
        if not any(r[k] for k in ("verdict_changed", "band_changed", "level_changed"))
    ]
    print(f"  episodes with any in-window document: {len(retrieval_rows)} of {len(episodes)}")
    print(f"  of those, ablation moved nothing on: {len(moved_nothing)}")

    # --- ablation 3: calibration (F8) ---------------------------------------------------------
    # Section 22.7.3 pre-registered "evidence-derived confidence against a flat prior, scored the
    # same way". A first version declared this not applicable on the grounds that there is no raw
    # model self-report to compare against, which declines a comparison the pre-registration did
    # not ask for. The flat prior is a degenerate baseline that assigns every finding the corpus
    # mean, and both arms are banded by the same section 19.4 thresholds.
    #
    # What this can and cannot show is stated with the result. It is **not** a calibration
    # measurement in the strict sense: there is no ground truth for whether a band was right, so
    # nothing here says the evidence-derived band is well calibrated. What it measures is whether
    # the score carries information at all, which a constant cannot. And four of its five features
    # are derived from inputs to the verdict, which `EvidenceScore.circular_features` names and
    # which bounds how much the spread is worth.
    print("\nablation 3: calibration")
    scores = []
    for episode in episodes:
        bundle = build_bundle(episode.well, episode.onset, episode.offset, usable)
        run = investigate(episode, bundle, index, documents, FactLedger())
        if run.finding is not None:
            scores.append(score_finding(run.finding, bundle))

    evidence_bands = Counter(str(s.band) for s in scores)
    flat_score = sum(s.score for s in scores) / len(scores) if scores else 0.0
    flat_band = (
        "high" if flat_score >= HIGH_BAND else "moderate" if flat_score >= MODERATE_BAND else "low"
    )
    spread = max((s.score for s in scores), default=0.0) - min(
        (s.score for s in scores), default=0.0
    )
    print(f"  evidence-derived bands: {dict(evidence_bands)}")
    print(f"  flat prior at the corpus mean {flat_score:.4f}: all {len(scores)} in {flat_band!r}")
    print(f"  score spread: {spread:.4f}")

    calibration: dict[str, Any] = {
        "available": True,
        "findings_scored": len(scores),
        "evidence_derived_bands": dict(evidence_bands),
        "flat_prior_score": flat_score,
        "flat_prior_band": flat_band,
        "flat_prior_bands": {flat_band: len(scores)},
        "score_spread": spread,
        "circular_features": list(scores[0].circular_features) if scores else [],
        "note": (
            "A flat prior assigns every finding the corpus mean, so it places all of them in one "
            "band by construction and the comparison measures whether the evidence score carries "
            "information rather than whether it is well calibrated. There is no ground truth here "
            "for whether a band was right, so nothing in this row supports a calibration claim. "
            "Four of the five features are derived from inputs to the verdict, which bounds what "
            "the spread is worth."
        ),
    }

    # --- ablation 4: cost and latency (F13) ---------------------------------------------------
    print("\nablation 4: cost and latency")
    # Two timers, because one would be misleading. `investigate` runs over a bundle that is
    # already built, and building it is the part that touches the production history. Reporting
    # only the controller would publish a latency figure that no caller could ever observe.
    controller_times: list[float] = []
    bundle_times: list[float] = []
    stages: list[int] = []
    for episode in episodes:
        started = time.perf_counter()
        bundle = build_bundle(episode.well, episode.onset, episode.offset, usable)
        bundle_times.append(time.perf_counter() - started)
        started = time.perf_counter()
        run = investigate(episode, bundle, index, documents, FactLedger())
        controller_times.append(time.perf_counter() - started)
        stages.append(len(run.trace.steps))

    def percentiles(values: list[float]) -> tuple[float, float]:
        """Median and the 95th-percentile order statistic.

        At n=14 the second index is 13, the maximum. That is what a 95th percentile of fourteen
        samples is, and the manifest records the sample count beside the figure so a reader can
        see it rather than inferring a smoothness that is not there.
        """
        ordered = sorted(values)
        return (
            ordered[len(ordered) // 2],
            ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        )

    p50, p95 = percentiles(controller_times)
    bundle_p50, bundle_p95 = percentiles(bundle_times)
    end_to_end = [b + c for b, c in zip(bundle_times, controller_times, strict=True)]
    total_p50, total_p95 = percentiles(end_to_end)
    print(f"  controller   p50 {p50 * 1000:.1f} ms   p95 {p95 * 1000:.1f} ms")
    print(f"  bundle       p50 {bundle_p50 * 1000:.1f} ms   p95 {bundle_p95 * 1000:.1f} ms")
    print(f"  end to end   p50 {total_p50 * 1000:.1f} ms   p95 {total_p95 * 1000:.1f} ms")
    print(f"  over {len(controller_times)} investigations, {min(stages)} to {max(stages)} steps")

    manifest: dict[str, Any] = {
        "generated": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
        # Recorded like every other manifest in this project. Its absence here meant nothing in
        # the file would let a reader notice it had been written by an older script.
        "commit_sha": _commit(),
        "protocol_version": CONSOLE_PROTOCOL_VERSION,
        "development_only": True,
        "expectation": {
            "rows": expectation_rows,
            # Published so the console's table can source its row count to a manifest key rather
            # than counting the list itself. Section 21.1: the console renders and does not
            # compute, and `len(rows)` in the assembler is computing.
            "model_count": len(expectation_rows),
            "note": (
                "episodes_opened is the measurement a WAPE cannot make: a model that expects too "
                "much manufactures investigations for a human to read."
            ),
        },
        "retrieval": {
            "rows": retrieval_rows,
            "episodes_total": len(episodes),
            "episodes_with_documents": len(retrieval_rows),
            "episode_document_counts": episode_document_counts,
            "episodes_where_nothing_moved": len(moved_nothing),
            "note": (
                "ADR 0008: most episodes have no in-window document, so the ablation population "
                "is the minority that do. An ablation over this few episodes measures these "
                "episodes and is not evidence about retrieval in general."
            ),
        },
        "calibration": calibration,
        "cost_and_latency": {
            "investigations": len(controller_times),
            "controller_p50_seconds": p50,
            "controller_p95_seconds": p95,
            "bundle_p50_seconds": bundle_p50,
            "bundle_p95_seconds": bundle_p95,
            "end_to_end_p50_seconds": total_p50,
            "end_to_end_p95_seconds": total_p95,
            "min_steps": min(stages),
            "max_steps": max(stages),
            "note": (
                "Two timers. The controller runs over a bundle that is already built, and "
                "building it is what touches the production history, so a controller-only figure "
                "is one no caller could observe. Neither includes loading the workbook. At 14 "
                "samples the 95th-percentile order statistic is the maximum, which is what a p95 "
                "of fourteen is; the count is published beside it."
            ),
            "not_applicable": COST_NOT_APPLICABLE,
        },
    }
    args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\nablation manifest written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
