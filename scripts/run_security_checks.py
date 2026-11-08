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

from volve_ops.console.assemble import CONSOLE_PROTOCOL_VERSION
from volve_ops.console.limits import NOT_APPLICABLE, declared_limits
from volve_ops.console.store import RunStore
from volve_ops.security import suite
from volve_ops.security.attacks import ARCHIVE_ATTACKS, PARSES_CORRECTLY, XML_ATTACKS
from volve_ops.security.claims import CLAIM_PATTERNS
from volve_ops.security.claims import files_scanned as claim_files
from volve_ops.security.claims import scan as claim_scan
from volve_ops.security.invariants import ALL_INVARIANTS, Status
from volve_ops.security.payloads import ALL_PAYLOADS, InjectionClass, payloads_of
from volve_ops.security.provenance_failures import (
    FAILURE_CLASSES,
    contradictions_in_console,
    health_contradictions,
)
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
    # folded into a pass.
    #
    # What runs on every push, with no dataset, is `TestClassThreeOverManifestPaths` in
    # tests/test_security.py: it builds synthetic manifests and makes the value check fail six
    # ways. That matters because the earlier claim here — that the checks run through
    # tests/test_health_payload.py — was false: that whole module skips without `data/cache/`, so
    # mark 11's value half ran in neither the harness nor the tests.
    store = RunStore(cache=args.cache, traces=args.cache / "investigations")
    have_artifacts = (args.cache / "investigation_run.json").exists() and (
        args.cache / "investigations"
    ).is_dir()

    print("\nmark 8: provenance failures")
    contradictions: tuple[Any, ...] = ()
    class_3_ran = False
    health_half_ran = False
    if not have_artifacts:
        print("  cached run artifacts absent. Skipped, not passed.")
    else:
        try:
            per_episode = contradictions_in_console(store)
            health_found, health_half_ran = health_contradictions(store)
            contradictions = (*per_episode, *health_found)
            class_3_ran = True
        except Exception as exc:
            print(f"  ! could not read the console payloads: {exc}")
            failures.append(f"mark 8: class 3 could not run: {exc}")
    if class_3_ran:
        # Reported separately. The per-episode half runs without the section 22 manifests and the
        # health half cannot, so one flag covering both said a check had run when half of it had
        # been skipped — which is what a first-ever run always looks like.
        print(f"  health screen walked: {health_half_ran}")
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

    # --- mark 9: every ablation reported something -------------------------------------------
    #
    # Section 22.4's preamble says every mark fails the build when it fails, and this one gated
    # nothing: the ablation manifest was read by the console and, for key existence, by mark 11.
    # Amendment 12 records what that let through — an ablation that silently dropped half its
    # population and published the survivor's count under the other population's label.
    print("\nmark 9: ablations")
    ablation_ran = False
    if not (args.cache / "ablation_run.json").exists():
        print("  ablation manifest absent. Skipped, not passed.")
    else:
        ablation: dict[str, Any] = json.loads(
            (args.cache / "ablation_run.json").read_text(encoding="utf-8")
        )
        ablation_ran = True
        for name in ("expectation", "retrieval", "calibration", "cost_and_latency"):
            if name not in ablation:
                failures.append(f"mark 9: the {name} ablation is absent from the manifest")
                print(f"  ! {name} absent")
                continue
            section = ablation[name]
            # An ablation reports rows, or it declares itself unavailable with a reason. Silence
            # is the one thing mark 9 forbids, because a dropped arm and an arm that moved
            # nothing look identical in a manifest that carries neither.
            reported = (
                bool(section.get("rows"))
                or section.get("available") is True
                or bool(section.get("investigations"))
            )
            if not reported and not section.get("reason"):
                failures.append(f"mark 9: the {name} ablation reported nothing and gave no reason")
                print(f"  ! {name} reported nothing")
            else:
                print(f"  {name}: reported")
        # The retrieval population is the figure amendment 12 records as having been wrong in
        # four places. Checking it against `len(rows)` is what the first version of this gate did,
        # and it is `len(x) == len(x)`: the harness writes both from the same list, so the check
        # would have passed on the buggy manifest it was written to catch.
        #
        # What can actually fail: the harness publishes a document count for **every** episode it
        # swept, including the ones it opened no arm for, so the population is reconciled against
        # the whole sweep rather than against the survivors.
        retrieval: dict[str, Any] = ablation.get("retrieval", {})
        document_counts: list[dict[str, Any]] | None = retrieval.get("episode_document_counts")
        if document_counts is None:
            failures.append(
                "mark 9: the retrieval ablation publishes no per-episode document count, so its "
                "population cannot be reconciled against the episodes it swept"
            )
            print("  ! no per-episode document counts")
        else:
            expected = sum(1 for c in document_counts if int(c["documents_in_window"]) > 0)
            published = retrieval.get("episodes_with_documents")
            if expected != published:
                failures.append(
                    f"mark 9: the retrieval population is {published} but {expected} of the "
                    "episodes swept have an in-window document"
                )
                print(f"  ! population {published} vs {expected}")
            if len(document_counts) != retrieval.get("episodes_total"):
                failures.append(
                    "mark 9: the retrieval document counts do not cover every episode swept"
                )
                print("  ! document counts do not cover the sweep")

    # --- mark 13: no claim of an operator safety case -----------------------------------------
    print("\nmark 13: overclaims")
    claims = claim_scan()
    claim_file_count = claim_files()
    print(f"  {len(claims)} claim(s) in {claim_file_count} files")
    if not claim_file_count:
        # The guard mark 2 has and this mark did not. Zero claims over zero files is not a pass,
        # and section 21.2 records what happens when a mark that examined nothing is read as one
        # that passed.
        failures.append("mark 13: the overclaim gate read no files at all")
    if claims:
        failures.append(f"mark 13: {len(claims)} overclaim(s)")
        for claim in claims:
            print(f"  ! {claim.file}:{claim.line} [{claim.pattern}] {claim.text}")

    manifest: dict[str, Any] = {
        "generated": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
        "commit_sha": _commit(),
        # Read from the document, never restated. A constant here put "protocol v16" on the
        # health screen while the console header read v17 from the same document: two screens of
        # one console disagreeing about which protocol they answer to, which is the conflation
        # amendment 9's lesson and assemble.CONSOLE_PROTOCOL_VERSION both exist to prevent.
        "protocol_version": CONSOLE_PROTOCOL_VERSION,
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
            "class_3_health_screen_walked": health_half_ran,
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
            "files_scanned": claim_file_count,
            "patterns": [name for name, _ in CLAIM_PATTERNS],
            "passed": not claims and bool(claim_file_count),
        },
        # Named for what it is. A bare `passed` beside a sub-block reporting `passed: false`
        # because it was skipped will be read at face value by the next reader or the next gate,
        # so the roll-up says only that the marks it could check here passed, and lists the ones
        # it could not. A skipped mark is never folded into either.
        "passed_checked_here": not failures,
        "skipped": [
            name
            for name, ran in (
                ("mark 8 class 3", class_3_ran),
                ("mark 8 class 3 over the health screen", health_half_ran),
                ("mark 9 ablations", ablation_ran),
                ("mark 11 health figures", health_ran),
            )
            if not ran
        ],
        "failures": failures,
    }
    # `data/` is gitignored, so a clean clone has no cache directory to write into. Every other
    # harness in this repository guards its write; this one did not, and it is the only section 22
    # step CI runs unconditionally, so it failed on a runner after printing a pass for every mark
    # it had checked.
    args.out.parent.mkdir(parents=True, exist_ok=True)
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
