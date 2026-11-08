"""Run protocol section 22's checks and publish what they found.

The System Health workspace renders these numbers and does not compute them, which is section
21.1 and mark 11. So every figure that reaches that screen is produced here and written to
`data/cache/security_run.json`, and the console reads it like any other manifest.

    python scripts/run_security_checks.py

Exits non-zero when a gating mark fails, so it can stand in a pipeline beside the console and
evaluation gates.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from volve_ops.console.limits import NOT_APPLICABLE, declared_limits
from volve_ops.console.store import RunStore
from volve_ops.security import suite
from volve_ops.security.attacks import ARCHIVE_ATTACKS, PARSES_CORRECTLY, XML_ATTACKS
from volve_ops.security.claims import CLAIM_PATTERNS
from volve_ops.security.claims import files_scanned as claim_files
from volve_ops.security.claims import scan as claim_scan
from volve_ops.security.invariants import ALL_INVARIANTS, Status
from volve_ops.security.payloads import ALL_PAYLOADS, InjectionClass, payloads_of
from volve_ops.security.provenance_failures import FAILURE_CLASSES, contradictions_in_console
from volve_ops.security.sinks import FORBIDDEN_SINKS, files_scanned, scan


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/cache/security_run.json"))
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    args = parser.parse_args(argv)

    failures: list[str] = []

    # --- mark 1: the injection suite ----------------------------------------------------------
    print("mark 1: injection invariants")
    with tempfile.TemporaryDirectory(prefix="volve-injection-") as workspace:
        report = suite.run(Path(workspace))
    counts = report.summary()
    for name, value in counts.items():
        print(f"  {name:<32} {value}")
    if not report.passed:
        failures.append("mark 1: the injection suite did not pass")
        for result in report.failures()[:10]:
            print(f"  ! {result.outcome.value} {result.invariant} / {result.payload}")

    # --- mark 2: the markup sink gate ---------------------------------------------------------
    print("\nmark 2: unescaped-markup sinks")
    sinks = scan()
    scanned = files_scanned()
    print(f"  {len(sinks)} sink(s) in {len(scanned)} frontend files")
    if sinks:
        failures.append(f"mark 2: {len(sinks)} markup sink(s) in the frontend")
        for occurrence in sinks:
            print(f"  ! {occurrence.file}:{occurrence.line} {occurrence.sink}")
    if not scanned:
        # A scan of nothing passes. Section 21.2 records what happens when a mark that examined
        # nothing is read as a mark that passed.
        failures.append("mark 2: the sink gate read no files at all")

    # --- mark 5: the attack corpus ------------------------------------------------------------
    # Counted rather than re-run here: the refusals are asserted in tests/test_security.py, where
    # each fixture is built and put to the parser. Publishing the count without the assertion
    # would be a number with nothing behind it, so the test ids are published with it.
    print("\nmark 5: attack corpus")
    print(
        f"  {len(XML_ATTACKS)} xml, {len(ARCHIVE_ATTACKS)} archive, "
        f"{len(PARSES_CORRECTLY)} must-parse"
    )

    # --- marks 8 and 11: the two that need the run artifacts -----------------------------------
    #
    # Both read artifacts the harnesses write, and `data/` is not committed, so on a runner there
    # is nothing for them to read. They report a skip and record `ran: false`; neither is ever
    # folded into a pass. The checks themselves run on every push through
    # tests/test_provenance_failures.py and tests/test_health_payload.py, which make each fail.
    store = RunStore(cache=args.cache, traces=args.cache / "investigations")
    have_artifacts = (args.cache / "investigation_run.json").exists() and (
        args.cache / "investigations"
    ).is_dir()

    print("\nmark 8: provenance failures")
    contradictions: tuple[Any, ...] = ()
    class_3_ran = False
    if not have_artifacts:
        print("  cached run artifacts absent. Skipped, not passed.")
    else:
        try:
            contradictions = contradictions_in_console(store)
            class_3_ran = True
        except Exception as exc:
            print(f"  ! could not read the console payloads: {exc}")
            failures.append(f"mark 8: class 3 could not run: {exc}")
    if class_3_ran:
        print(f"  class 3, figures contradicting their records: {len(contradictions)}")
        if contradictions:
            failures.append(f"mark 8: {len(contradictions)} figure(s) contradict their records")
            for contradiction in contradictions[:5]:
                print(f"  ! {contradiction}")

    print("\nmark 11: health figures resolve to a manifest")
    health_examined = 0
    health_ran = False
    if not have_artifacts or not (args.cache / "ablation_run.json").exists():
        print("  section 22 manifests absent. Skipped, not passed.")
    else:
        try:
            from volve_ops.console import assemble, gates

            facts: set[str] = set()
            for path in (args.cache / "investigations").glob("*.facts.json"):
                facts |= {str(f["id"]) for f in json.loads(path.read_text(encoding="utf-8"))}
            outcome = gates.figures_resolve(
                {"system_health": assemble.system_health(store)},
                store.health_manifests(),
                fact_ids=frozenset(facts),
                artifacts=args.cache / "investigations",
            )
            health_examined = outcome.examined
            health_ran = True
            verdict = "pass" if outcome.passed else "FAIL"
            print(f"  {outcome.examined} source(s) examined, {verdict}")
            if not outcome.passed:
                failures.append("mark 11: a health figure does not resolve")
                for detail in outcome.detail:
                    print(f"  ! {detail}")
        except Exception as exc:
            print(f"  ! could not assemble the health payload: {exc}")
            failures.append(f"mark 11: {exc}")

    # --- mark 13: no claim of an operator safety case -----------------------------------------
    print("\nmark 13: overclaims")
    claims = claim_scan()
    print(f"  {len(claims)} claim(s) in {claim_files()} files")
    if claims:
        failures.append(f"mark 13: {len(claims)} overclaim(s)")
        for claim in claims:
            print(f"  ! {claim.file}:{claim.line} [{claim.pattern}] {claim.text}")

    manifest: dict[str, Any] = {
        "generated": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
        "commit_sha": _commit(),
        "protocol_version": "v16",
        "injection": {
            **counts,
            "payloads": len(ALL_PAYLOADS),
            "payloads_by_class": {str(c.value): len(payloads_of(c)) for c in InjectionClass},
            "invariants_declared": len(ALL_INVARIANTS),
            "vacuous": [
                {"key": i.key, "wording": i.brief_wording, "reason": i.reason}
                for i in ALL_INVARIANTS
                if i.status is Status.VACUOUS
            ],
            "passed": report.passed,
        },
        "markup_sinks": {
            "found": len(sinks),
            "files_scanned": len(scanned),
            "forbidden": list(FORBIDDEN_SINKS),
            "passed": not sinks and bool(scanned),
        },
        "attack_corpus": {
            "xml_fixtures": len(XML_ATTACKS),
            "archive_fixtures": len(ARCHIVE_ATTACKS),
            "must_parse_fixtures": len(PARSES_CORRECTLY),
            "asserted_in": "tests/test_security.py::TestTheAttackCorpus",
        },
        "provenance_failures": {
            "classes": len(FAILURE_CLASSES),
            "class_3_ran": class_3_ran,
            "class_3_contradictions": len(contradictions) if class_3_ran else None,
            "detail": [str(c) for c in contradictions[:20]],
            "asserted_in": "tests/test_provenance_failures.py",
        },
        "limits": {**declared_limits(), "not_applicable": NOT_APPLICABLE},
        "health_figures": {
            "ran": health_ran,
            "sources_examined": health_examined,
            "passed": health_ran and not any(f.startswith("mark 11") for f in failures),
        },
        "overclaims": {
            "found": len(claims),
            "files_scanned": claim_files(),
            "patterns": [name for name, _ in CLAIM_PATTERNS],
            "passed": not claims,
        },
        "passed": not failures,
        "failures": failures,
    }
    args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\nsecurity manifest written to {args.out}")

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("\nall section 22 marks checked here pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
