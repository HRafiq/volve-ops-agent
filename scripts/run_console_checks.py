"""Run the operator console's checks and report protocol section 21.6.

    python scripts/run_console_checks.py

Calls no model. Exit status is the gate: non-zero when any section 21.6 pass mark fails.

Assembles every payload the API serves, through the same functions the API routes call, and puts
the eight marks to them. Assembling rather than requesting, so the harness needs no running server
and the deterministic CI job can run it.

What the harness does **not** do is define any mark. Each one is a function in
`volve_ops.console.gates` with a test that makes it fail, which is the one structural lesson of the
five phases before this: a gate written as an expression in the script that produces the thing it
checks cannot fail, and no amount of care substitutes for moving it out.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from volve_ops.console import assemble, gates
from volve_ops.console.assemble import CONSOLE_PROTOCOL_VERSION
from volve_ops.console.priority import Scored, score_episode, term_counts
from volve_ops.console.review import ReviewLog
from volve_ops.console.store import RunStore, investigation_id

#: The design mockup, which is local-only. Section 21.2's mark extracts its placeholder figures at
#: check time rather than listing them in a tracked file, and reports examining nothing when it is
#: absent so that a skipped check is not mistaken for a passed one.
DEFAULT_MOCKUP = Path("_private/mockup/VolveOpsConsole.jsx")


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--traces", type=Path, default=Path("data/cache/investigations"))
    parser.add_argument("--mockup", type=Path, default=DEFAULT_MOCKUP)
    parser.add_argument("--manifest", type=Path, default=Path("data/cache/console_run.json"))
    args = parser.parse_args(argv)

    store = RunStore(cache=args.cache, traces=args.traces)
    manifests = store.manifests()
    queue = assemble.queue(store)
    header = assemble.header(store)
    details = {
        row.investigation_id: assemble.detail(store, row.investigation_id) for row in queue.rows
    }

    print(f"payloads      queue with {len(queue.rows)} rows, header, {len(details)} detail screens")
    print(f"              {len(queue.kpis)} KPI tiles on the production strip")

    payloads: dict[str, Any] = {"queue": queue, "header": header, **details}
    rendered = {name: payload.model_dump_json() for name, payload in payloads.items()}
    fact_ids: frozenset[str] = frozenset()
    for detail in details.values():
        fact_ids |= store.resolvable_ids(detail.well, detail.period.split(" to ")[0])

    scored: list[Scored] = [
        score_episode(
            well=str(row["well"]),
            onset=str(row["onset"]),
            cumulative_shortfall_sm3=float(row["cumulative_rate_shortfall_sm3"]),
            episode_days=int(row["episode_days"]),
            verdict=str(row["verdict"]),
            evidence_band=assemble._band_for(
                store.evaluation(), str(row["well"]), str(row["onset"])
            ),
            review_state=ReviewLog().state_of(
                investigation_id(str(row["well"]), str(row["onset"]))
            ),
        )
        for row in store.episodes()
    ]

    print("\npriority, section 21.5 and ADR 0009:")
    for name, count in term_counts(scored).items():
        print(f"  {count:>4}  {name}")
    for band in ("HIGH", "MEDIUM", "LOW"):
        rows = [s for s in scored if s.priority.value == band]
        print(f"  {band:<7} {len(rows)}")
    print("  the review term fires on nothing until someone uses the console. Section 21.5")
    print("  requires both of ADR 0009's measurements wherever the rule is printed: the disputed")
    print("  clause changes no episode's band on this data, AND removing the term leaves the queue")
    print("  with no HIGH case, so it is undetectable between its forms and load-bearing against")
    print("  its absence. The first alone reads as the term being inert, which it is not.")

    with tempfile.TemporaryDirectory() as scratch:
        probe_log = ReviewLog(Path(scratch) / "probe.jsonl")
        routes = _route_table()
        outcomes = [
            gates.figures_resolve(payloads, manifests, fact_ids=fact_ids, artifacts=args.traces),
            gates.no_placeholder_appears(rendered, args.mockup),
            gates.no_hold_out_well(rendered),
            gates.abstention_renders(
                [
                    (row.investigation_id, row.assessment, details[row.investigation_id].coverage)
                    for row in queue.rows
                ]
            ),
            gates.money_carries_its_assumption(
                [(tile.label, tile.money) for tile in queue.kpis if tile.money is not None]
            ),
            gates.review_log_is_append_only(probe_log),
            gates.api_is_read_only(routes),
            gates.priority_matches_the_printed_rule(
                [
                    (
                        row.investigation_id,
                        int(row.priority_score.value or 0),
                        float(row.cumulative_shortfall.value or 0.0),
                        int(row.episode_days.value or 0),
                        row.assessment,
                        row.evidence_strength,
                        # The payload's own state, not a literal. Passing "none" here made the
                        # gate agree with the payload by construction on the review term, which is
                        # the one term that was broken: the queue never read the log at all.
                        row.review_state,
                    )
                    for row in queue.rows
                ],
                queue.rule.statement,
            ),
        ]

    print("\nsection 21.6 pass marks:")
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

    words = gates.operator_screens_avoid_engineering_words(rendered)
    print(f"\nengineering vocabulary on operator screens: {len(words)} occurrence(s)")
    for line in words[:8]:
        print(f"  ! {line}")
    print("  reported and not gated: section 21.6 has eight marks and inventing a ninth after the")
    print("  fact is the move amendment 7 was written about")

    marks = {outcome.name: outcome.passed for outcome in outcomes}
    payload = {
        # Recorded like every other manifest in this project. This one carried neither, so
        # nothing in it would let a reader notice it had been written by an older script or
        # against a different tree.
        "generated": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
        "commit_sha": _commit(),
        # Read from the document. A constant here is the defect amendment 9 named and round 2 of
        # the phase 7 review fixed in run_security_checks.py; the same line one file over was
        # left at v14 while the document was at v17.
        "protocol_version": CONSOLE_PROTOCOL_VERSION,
        "console_version": "console-v0",
        "queue_rows": len(queue.rows),
        "detail_screens": len(details),
        "kpi_tiles": len(queue.kpis),
        "sources_checked": outcomes[0].examined,
        "placeholder_figures_compared": outcomes[1].examined,
        "abstentions_checked": outcomes[3].examined,
        "routes": len(routes),
        "priority_bands": {
            band: sum(1 for s in scored if s.priority.value == band)
            for band in ("HIGH", "MEDIUM", "LOW")
        },
        "priority_term_counts": term_counts(scored),
        "engineering_words_on_operator_screens": len(words),
        "gates_that_examined_nothing": vacuous,
        "pass_marks": marks,
        "all_pass": all(marks.values()),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nrun manifest written to {args.manifest}")
    return 0 if all(marks.values()) else 1


def _route_table() -> list[tuple[str, frozenset[str]]]:
    """The API's own route table, for section 21.6 mark 7.

    The import is deferred rather than top-level because `api.main` needs FastAPI, which is an
    optional dependency: every other mark here is checkable without a web framework, and making the
    whole gate set unavailable because one of eight needs one would be the wrong trade.

    **The two reasons it can fail are reported separately.** The first version caught
    `ModuleNotFoundError` and printed "fastapi is not installed" either way, which was false on the
    run that found it: FastAPI was installed and the repository root was not on the path, so the
    mark examined nothing and pointed the reader at a dependency that was fine.
    """
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from api.main import route_table
    except ModuleNotFoundError as missing:
        if missing.name == "fastapi":
            print("  mark 7 examines no routes: fastapi is not installed (the `console` extra)")
        else:
            print(f"  mark 7 examines no routes: cannot import {missing.name!r} from {root}")
        return []
    return route_table()


if __name__ == "__main__":
    raise SystemExit(main())
