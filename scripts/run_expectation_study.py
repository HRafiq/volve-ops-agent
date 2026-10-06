"""Produce the expectation-engine results, reproducibly.

This script is the committed entry point behind `docs/expectation_results.md`. Before it
existed, the figures in that document could not be regenerated from the repository, which for a
project whose claim is reproducibility is a hole in the claim rather than a missing convenience.

It also emits a run manifest. Section 12 of the protocol requires one beside any headline
result, and says plainly that a result which cannot be traced to a complete manifest is not
reported as a result.

Everything here runs on development data only. The split is derived from the record and applied
at the source, so the hold-out cannot be reached by forgetting to filter.

    python scripts/run_expectation_study.py data/cache/Volve\\ production\\ data.xlsx \\
        data/cache/ddr_xml
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from volve_ops import INGEST_VERSION
from volve_ops.domain.activity import activity_dates_by_well
from volve_ops.domain.backtest import (
    HORIZONS,
    condition_1_relative_wape,
    condition_2_lower_tail,
    condition_3_bias,
    run_backtest,
)
from volve_ops.domain.day_class import DayClass
from volve_ops.domain.episodes import sweep_well
from volve_ops.domain.expectation import CANDIDATE_MODELS, NaiveMedian28
from volve_ops.domain.production_service import load_volve_production
from volve_ops.domain.regimes import stable_reference_windows
from volve_ops.domain.splits import cold_start_wells, derive_split, development_only
from volve_ops.domain.well_naming import well_of

BASELINE_NAMES = ("naive-median28", "naive-persistence")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("report_dir", type=Path)
    # Defaulted rather than optional. With no default this script wrote no manifest unless asked,
    # so the evaluation harness audited a stale one and never saw the dates this run fitted on.
    parser.add_argument("--manifest", type=Path, default=Path("data/cache/run_manifest.json"))
    args = parser.parse_args(argv)

    history = load_volve_production(args.workbook)
    activity = activity_dates_by_well(args.report_dir)
    split = derive_split(history.days)

    producers = sorted(
        {d.day.well for d in history.days if d.day_class is DayClass.VALID_PRODUCING}
    )
    full = {w: history.for_well(w) for w in producers}
    development = {w: development_only(full[w], split) for w in producers}
    # Wells that actually produce. `if days` kept any well with a development row, which retained
    # 15/9-F-5: a water injector with 2,429 development rows and zero valid producing days. It got
    # no stable window and no fit, so nothing it touched moved, but it inflated every "producing
    # wells" figure by one and put a section 16 hold-out well into the population.
    usable = {
        w: days
        for w, days in development.items()
        if any(d.day_class is DayClass.VALID_PRODUCING for d in days)
    }
    windows = {
        w: stable_reference_windows(days, activity_dates=activity.get(well_of(w), set()))
        for w, days in usable.items()
    }

    print(f"record        {split.record_start} .. {split.record_end} ({split.span_days} days)")
    print(f"boundary      {split.boundary}")
    print(f"development   ends {split.development_end} (90-day buffer)")
    print(f"producers     {len(producers)}; cold start {cold_start_wells(full, split)}")
    print()
    for well in sorted(usable):
        valid = sum(1 for d in usable[well] if d.day_class is DayClass.VALID_PRODUCING)
        print(
            f"  {well:<14} development valid days {valid:>5}"
            f"   stable windows {len(windows[well]):>3}"
        )

    results = run_backtest(usable, windows)
    baselines = [results[name] for name in BASELINE_NAMES if name in results]

    print(
        f"\n{'model':<22}" + "".join(f"{'WAPE H=' + str(h):>13}" for h in HORIZONS) + f"{'days':>9}"
    )
    for name, result in results.items():
        cells = "".join(
            f"{value:>13.4f}" if (value := result.pooled_wape(h)) is not None else f"{'-':>13}"
            for h in HORIZONS
        )
        print(f"{name:<22}{cells}{len(result.evaluated):>9}")

    print("\nselection, against the pre-registered conditions:")
    selected = None
    for name, result in results.items():
        if name in BASELINE_NAMES:
            continue
        outcomes = [
            condition_1_relative_wape(result, baselines),
            condition_2_lower_tail(result, producer_count=len(producers)),
            condition_3_bias(result),
        ]
        verdict = all(o.passed for o in outcomes)
        print(f"\n  {name}: {'PASSES' if verdict else 'does not pass'}")
        for outcome in outcomes:
            print(f"    {outcome.name:<26}{'pass' if outcome.passed else 'fail'}")
            print(f"      {outcome.detail[:400]}")
        if verdict and selected is None:
            selected = name

    if selected is None:
        selected = "naive-median28"
        print(f"\n  no candidate passes; the protocol's fallback applies: {selected}")

    model = (
        NaiveMedian28()
        if selected == "naive-median28"
        else next(m for m in CANDIDATE_MODELS if m.name == selected)
    )
    print(f"\nepisodes opened by {selected} on development data:")
    episodes = []
    for well in sorted(usable):
        found = sweep_well(well, usable[well], windows[well], model)
        episodes.extend(found)
        for episode in found:
            flags = " OPEN-ENDED" if episode.open_ended else ""
            flags += " POORLY-EVIDENCED" if episode.poorly_evidenced else ""
            print(
                f"  {episode.well:<14}{episode.onset} .. {episode.offset}"
                f"  {episode.valid_producing_days:>4} vpd"
                f"  shortfall {episode.cumulative_rate_shortfall_sm3:>11,.0f}"
                f"  (bar {episode.shortfall_threshold_sm3:>10,.0f})"
                f"  deferred {episode.deferred_volume_sm3:>9,.0f}"
                f"  gaps {episode.gap_fraction:.0%}{flags}"
            )
    print(f"  total {len(episodes)}")

    manifest: dict[str, Any] = {
        "generated": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
        "commit_sha": _commit(),
        "dataset_version": {
            "workbook": {"path": args.workbook.name, "sha256": _sha256(args.workbook)},
            "drilling_reports": {
                "files": len(list(args.report_dir.glob("*.xml"))),
                "directory": args.report_dir.name,
            },
        },
        "parser_version": INGEST_VERSION,
        "protocol_version": "v1",
        "split": {
            "record_start": split.record_start.isoformat(),
            "record_end": split.record_end.isoformat(),
            "boundary": split.boundary.isoformat(),
            "development_end": split.development_end.isoformat(),
        },
        "horizons": list(HORIZONS),
        "candidates": [m.name for m in CANDIDATE_MODELS],
        "selected_model": selected,
        "wape": {
            name: {str(h): result.pooled_wape(h) for h in HORIZONS}
            for name, result in results.items()
        },
        "evaluated_days": {name: len(r.evaluated) for name, r in results.items()},
        "episodes": len(episodes),
        # Every date this run actually fitted and swept on, per well. Recorded so that protocol
        # section 19.2's third leakage check can test the dates a script used rather than
        # re-deriving them with the same filter it is meant to be auditing. Independent review
        # showed the audit could not otherwise see a leak here at all: it was testing the negation
        # of the comprehension that produced its own input.
        "fitted_day_dates": {
            well: sorted(d.day.production_date.isoformat() for d in days)
            for well, days in sorted(usable.items())
        },
    }
    target = args.manifest or Path("run_manifest.json")
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\nrun manifest written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
