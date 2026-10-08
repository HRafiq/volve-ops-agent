"""Run the investigation layer over the development episodes and check protocol section 18.7.

The committed entry point behind docs/investigation_results.md.

    python scripts/run_investigations.py "data/cache/Volve production data.xlsx" \
        data/cache/ddr_xml --store data/cache/npt_store

Everything runs on development data. The split is applied at the source, so the hold-out cannot be
reached by forgetting to filter, and section 18.9 keeps it out of this phase entirely.

No model is called. The judgement role is the deterministic one fixed in the controller, which is
also the floor a model-backed role has to beat: an investigation whose correctness depended on a
model would be one nobody could test, and section 18.6 needs an opponent that existed first.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any

from volve_ops.domain.activity import activity_dates_by_well
from volve_ops.domain.day_class import DayClass
from volve_ops.domain.episodes import sweep_well
from volve_ops.domain.expectation import NaiveMedian28
from volve_ops.domain.production_service import load_volve_production
from volve_ops.domain.regimes import stable_reference_windows
from volve_ops.domain.splits import derive_split, development_only
from volve_ops.domain.well_naming import well_of
from volve_ops.extraction.store import EventStore
from volve_ops.investigation import baseline
from volve_ops.investigation.controller import (
    EVIDENCE_WINDOW_DAYS,
    ReplayJudgement,
    investigate,
)
from volve_ops.investigation.diagnostics import build_bundle
from volve_ops.investigation.schemas import (
    CausalLevel,
    Finding,
    HypothesisStatus,
    StopReason,
    Verdict,
    forbidden_root_cause_wording,
)
from volve_ops.investigation.trace import Stage, Trace
from volve_ops.investigation.validator import CitableDocument, check
from volve_ops.provenance.facts import FactLedger
from volve_ops.retrieval.index import BM25Index, chunks_from_events


def stop_matches_trace(trace: Trace, finding: Finding) -> bool:
    """Whether the recorded steps support the stop condition the finding reports.

    Section 18.7 mark 2 asks whether the stop "matches the controller state that produced it". The
    first implementation compared the finding's `curtailed` flag against the frozenset it had just
    been derived from, which is a tautology. This reads the trace instead.
    """
    if finding.stop_reason is StopReason.STEP_BUDGET_REACHED:
        return finding.curtailed and len(trace.steps) >= 1
    if finding.stop_reason is StopReason.COST_BUDGET_REACHED:
        return finding.curtailed and trace.cost_usd > 0.0
    if finding.stop_reason is StopReason.MANDATORY_EVIDENCE_UNAVAILABLE:
        return (
            finding.curtailed
            and bool(finding.unavailable_mandatory)
            and any("unavailable" in step.summary for step in trace.steps)
        )
    # The two settled endings must not be marked curtailed, and must follow a decision step.
    return not finding.curtailed and any(
        step.stage is Stage.DECIDE_CONTINUE for step in trace.steps
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("--store", type=Path, default=Path("data/cache/npt_store"))
    parser.add_argument("--version", default="extractor-v0")
    parser.add_argument("--traces", type=Path, default=Path("data/cache/investigations"))
    parser.add_argument("--manifest", type=Path, default=Path("data/cache/investigation_run.json"))
    parser.add_argument(
        "--oil-price-usd-per-sm3",
        type=float,
        default=None,
        help="a stated assumption; omitted means no value shortfall is computed at all",
    )
    args = parser.parse_args(argv)

    history = load_volve_production(args.workbook)
    split = derive_split(history.days)
    producers = sorted(
        {d.day.well for d in history.days if d.day_class is DayClass.VALID_PRODUCING}
    )
    # Wells that actually produce. `if days` kept any well with a development row, which put
    # 15/9-F-5 into the population: a water injector with 2,429 development rows and zero valid
    # producing days. Independent review found its rows reaching the offset comparison of all
    # fourteen findings, where they contributed nothing and were invisible to the leakage audit.
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

    episodes = []
    for well in sorted(usable):
        episodes.extend(sweep_well(well, usable[well], windows[well], NaiveMedian28()))

    events = list(EventStore(args.store).read(args.version))
    index = BM25Index(chunks_from_events(events))
    # The gate checks a citation's filename, well and date, not only its text, so it needs the
    # event's metadata rather than its comment alone.
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

    print(f"development wells {len(usable)}; episodes {len(episodes)}")
    print(f"narrative index   {len(index)} chunks over {len({e.well for e in events})} wells")
    print(f"evidence window   +/-{EVIDENCE_WINDOW_DAYS} days either side of an episode\n")

    rows: list[dict[str, Any]] = []
    gate_failures = 0
    replay_failures = 0
    wording_failures = 0
    args.traces.mkdir(parents=True, exist_ok=True)

    for episode in episodes:
        bundle = build_bundle(episode.well, episode.onset, episode.offset, usable)
        ledger = FactLedger()
        result = investigate(
            episode,
            bundle,
            index,
            documents,
            ledger,
            oil_price_usd_per_sm3=args.oil_price_usd_per_sm3,
        )
        finding = result.finding
        assert finding is not None

        gate = check(finding, ledger, documents)
        wording = forbidden_root_cause_wording(finding.narrative, finding.highest_level)
        replayed = investigate(
            episode,
            bundle,
            index,
            documents,
            FactLedger(),
            judgement=ReplayJudgement(result.trace),
            oil_price_usd_per_sm3=args.oil_price_usd_per_sm3,
        )
        replays = replayed.finding == finding
        call = baseline.call(bundle)

        gate_failures += 0 if gate.passed else 1
        replay_failures += 0 if replays else 1
        wording_failures += 1 if wording else 0

        slug = f"{episode.well.replace('/', '_').replace(' ', '_')}_{episode.onset}"
        result.trace.write(args.traces / f"{slug}.trace.json")
        (args.traces / f"{slug}.finding.json").write_text(
            finding.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )

        supported = [
            h.hypothesis_id for h in finding.hypotheses if h.status is HypothesisStatus.SUPPORTED
        ]
        families = {
            baseline.HYPOTHESIS_FAMILY[h] for h in supported if h in baseline.HYPOTHESIS_FAMILY
        }
        citations = sum(len(h.supporting) for h in finding.hypotheses)
        print(
            f"  {episode.well} {episode.onset}  {finding.verdict.value:<32} "
            f"{finding.stop_reason.value:<31} gate {'pass' if gate.passed else 'BLOCK'}  "
            f"replay {'ok' if replays else 'DIFFERS'}  citations {citations}"
        )
        print(
            f"      supported {supported or 'none'}; unavailable "
            f"{[c.value for c in finding.unavailable_mandatory] or 'none'}; "
            f"baseline {call.proximate_driver or 'abstains'}"
        )
        for violation in gate.violations[:3]:
            print(f"      ! {violation.rule}: {violation.detail[:100]}")

        rows.append(
            {
                "well": episode.well,
                "onset": episode.onset.isoformat(),
                "offset": episode.offset.isoformat(),
                # The episode's own figures, published here because protocol section 21.1 confines
                # the console to rendering: the queue needs a shortfall and a duration per episode,
                # and the alternative is an API that recomputes them, which is the second
                # implementation sections 14.3 and 20.2 both had to retract a claim about.
                "episode_days": (episode.offset - episode.onset).days + 1,
                "cumulative_rate_shortfall_sm3": round(episode.cumulative_rate_shortfall_sm3, 2),
                "deferred_volume_sm3": round(episode.deferred_volume_sm3, 2),
                "reference_rate_sm3_per_day": round(episode.reference_rate_sm3_per_day, 2),
                "shortfall_threshold_sm3": round(episode.shortfall_threshold_sm3, 2),
                "gap_fraction": round(episode.gap_fraction, 4),
                "poorly_evidenced": episode.poorly_evidenced,
                "open_ended": episode.open_ended,
                "valid_producing_days": episode.valid_producing_days,
                "verdict": finding.verdict.value,
                "stop_reason": finding.stop_reason.value,
                "curtailed": finding.curtailed,
                "highest_level": finding.highest_level.value if finding.highest_level else None,
                "supported": supported,
                "citations": citations,
                "unavailable_mandatory": [c.value for c in finding.unavailable_mandatory],
                "gate_passed": gate.passed,
                "gate_violations": [v.model_dump(mode="json") for v in gate.violations],
                "replays_exactly": replays,
                "stop_matches_trace": stop_matches_trace(result.trace, finding),
                "baseline_driver": call.proximate_driver,
                "baseline_abstained": call.abstained,
                # Compared at the level of the physical event, not the column. See
                # baseline.DRIVER_FAMILY.
                #
                # None only where one side named nothing. Review caught the first version returning
                # None when the controller's supported hypothesis lay outside the baseline's
                # vocabulary, which silently dropped the one episode where the two named different
                # drivers and turned 5 of 7 into 5 of 6, the most favourable of three framings.
                "agrees_with_baseline": (
                    None if call.family is None or not supported else call.family in families
                ),
                "supported_families": sorted(families),
            }
        )

    # Counters over closed vocabularies, filled out to the whole enum so that a value nothing
    # reached is published as 0 rather than omitted. A `Counter` omits what it never saw, and two
    # stop conditions were therefore absent from the manifest while the results table carried a row
    # for each, which rendered as "not produced". A stop condition nothing reached is a result: it
    # says the budget was never the binding constraint, which is section 18.3's whole question.
    verdicts = collections.Counter(r["verdict"] for r in rows)
    verdicts.update({v.value: 0 for v in Verdict})
    stops = collections.Counter(r["stop_reason"] for r in rows)
    stops.update({s.value: 0 for s in StopReason})
    levels = collections.Counter(str(r["highest_level"]) for r in rows)
    levels.update({c.value: 0 for c in CausalLevel})
    levels.update({"None": 0})
    citations = sum(int(r["citations"]) for r in rows)
    comparable = [r for r in rows if r["agrees_with_baseline"] is not None]
    agree = sum(1 for r in comparable if r["agrees_with_baseline"])

    print("\nverdicts:")
    for name, count in verdicts.most_common():
        print(f"  {count:>4}  {name}")
    print("stop conditions:")
    for name, count in stops.most_common():
        print(f"  {count:>4}  {name}")
    print("highest causal level reached:")
    for name, count in levels.most_common():
        print(f"  {count:>4}  {name}")
    print(f"\ndocument citations across all {len(rows)} findings: {citations}")
    print(
        f"agreement with {baseline.BASELINE_NAME} on the driver family: "
        f"{agree}/{len(comparable)} of the episodes where both named one"
    )

    print("\nsection 18.7 pass marks:")
    marks = {
        "provenance validity is 100 percent": gate_failures == 0,
        # Checked against the trace that produced the finding, not against the finding's own
        # `curtailed` flag. The first version compared `curtailed` with the frozenset the controller
        # had just set it from, so it was a value tested against its own definition and could not
        # fail. What it checks now: the stop the finding reports is one the recorded steps support.
        "stop-condition honesty is 100 percent": all(r["stop_matches_trace"] for r in rows),
        "trace replay is exact": replay_failures == 0,
        "abstention is reachable and used": verdicts[Verdict.INSUFFICIENT_EVIDENCE.value] > 0,
        "no forbidden root-cause wording": wording_failures == 0,
    }
    for name, passed in marks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")

    # Aggregates the console's Production KPI strip shows. Published here rather than summed in the
    # API, for protocol section 21.1's reason: a figure an operator reads has to come from a run
    # manifest, and a sum computed in a serving layer has no gate on it.
    total_shortfall = sum(float(r["cumulative_rate_shortfall_sm3"]) for r in rows)
    total_deferred = sum(float(r["deferred_volume_sm3"]) for r in rows)
    no_conclusion = sum(1 for r in rows if r["verdict"] == Verdict.INSUFFICIENT_EVIDENCE.value)
    unresolved = sum(1 for r in rows if r["verdict"] != Verdict.SUPPORTED_EXPLANATION.value)

    payload: dict[str, Any] = {
        "protocol_version": "v12",
        "episodes": len(rows),
        "wells_with_an_episode": len({r["well"] for r in rows}),
        "cumulative_rate_shortfall_sm3": round(total_shortfall, 2),
        "deferred_volume_sm3": round(total_deferred, 2),
        "episodes_with_no_conclusion": no_conclusion,
        "episodes_without_a_single_explanation": unresolved,
        "poorly_evidenced_episodes": sum(1 for r in rows if r["poorly_evidenced"]),
        "development_wells": sorted(usable),
        # As above: the dates this run actually built bundles over. The offset comparison in
        # diagnostics reads every well in this population, so a hold-out well present here reaches
        # every finding even when it produces no episode of its own.
        "bundle_day_dates": {
            well: sorted(d.day.production_date.isoformat() for d in days)
            for well, days in sorted(usable.items())
        },
        "evidence_window_days": EVIDENCE_WINDOW_DAYS,
        "indexed_chunks": len(index),
        "verdicts": dict(verdicts),
        "stop_conditions": dict(stops),
        "highest_levels": dict(levels),
        "document_citations": citations,
        "documented_root_cause_reached": levels.get(CausalLevel.DOCUMENTED_ROOT_CAUSE.value, 0),
        "baseline": baseline.BASELINE_NAME,
        "baseline_agreement": {"agree": agree, "comparable": len(comparable)},
        "pass_marks": marks,
        "all_pass": all(marks.values()),
        "findings": rows,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\ntraces and findings in {args.traces}")
    print(f"run manifest written to {args.manifest}")
    return 0 if all(marks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
