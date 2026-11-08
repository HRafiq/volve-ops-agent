"""Serve the console over artifacts carrying the injection corpus, for section 22.4 mark 3.

Mark 3 asks whether hostile text reaches the screen **as text**, and says the check is made
against the rendered output rather than against the assembler. So the payloads have to be in the
artifacts the console reads, and the console has to actually run.

Nothing here touches the real cache. The artifacts are copied to a temporary directory, the
payloads are written into the evidence spans of one episode, and the API's store dependency is
pointed at the copy. The review log is pointed at the copy too: it is append-only, so a run that
wrote to the real one would leave records a later run could cite and nothing could remove.

    python scripts/serve_injected_console.py --port 8765

Then the rendered DOM is inspected for each marker. A marker present as a text node with no
element, attribute or URL scheme derived from it is the invariant holding. The experiment id is
printed so the health tab's row can name the run that produced it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import uvicorn

# The repository root, so `api` imports when this is run as `python scripts/...` and sys.path[0]
# is the scripts directory rather than the root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from volve_ops.console.review import ReviewLog
from volve_ops.console.store import RunStore
from volve_ops.security.payloads import ALL_PAYLOADS, InjectionClass, Payload, payloads_of

#: The classes whose whole point is what a browser does with them.
RENDERED_CLASSES = (InjectionClass.MARKUP, InjectionClass.UNICODE_AND_ENCODING)


def rendered_payloads() -> tuple[Payload, ...]:
    return tuple(p for c in RENDERED_CLASSES for p in payloads_of(c))


def experiment_id(payloads: tuple[Payload, ...]) -> str:
    """A stable id for this corpus, so a health-tab row names the run that produced it."""
    digest = hashlib.sha256("\n".join(p.text for p in payloads).encode("utf-8")).hexdigest()
    return f"inj-render-{digest[:12]}"


def spans_in(finding: dict[str, Any]) -> int:
    """How many evidence spans a finding carries, which is how many the drawer renders."""
    return sum(
        1
        for hypothesis in finding.get("hypotheses", [])
        for ref in list(hypothesis.get("supporting", ()))
        + list(hypothesis.get("contradicting", ()))
        if ref.get("span")
    )


def inject(cache: Path, destination: Path, payloads: tuple[Payload, ...]) -> dict[str, Any]:
    """Copy the artifacts and write the corpus into the free-text fields the console renders.

    **The episode is chosen, not taken first.** Of the fourteen development episodes exactly one
    carries any evidence span: ADR 0008 established that most episodes have no in-window document,
    so most findings have nothing quoted and the drawer renders no document text for them. A first
    version of this script injected into the alphabetically first finding, which has no span at
    all, and delivered one payload out of sixteen to the narrative while reporting success. That is
    section 22.2's defect in the fixture rather than in the system, and it is the reason the choice
    is explicit here.

    Every payload goes into every field rather than one each. There are three renderable slots in
    the whole corpus and sixteen payloads, and the question each one asks is whether a browser
    interprets it, which is not a question about which slot it sat in.

    Returns what was injected where, so the DOM check knows which markers to look for.
    """
    shutil.copytree(cache, destination, dirs_exist_ok=True)
    traces = destination / "investigations"
    findings = sorted(traces.glob("*.finding.json"))
    if not findings:
        raise SystemExit(
            f"no finding artifacts under {traces}; run the investigation harness first"
        )

    loaded = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in findings]
    target, finding = max(loaded, key=lambda pair: spans_in(pair[1]))
    if spans_in(finding) == 0:
        raise SystemExit(
            "no finding in this cache carries an evidence span, so the drawer renders no document "
            "text and mark 3 has nothing to check. Re-run the investigation harness."
        )

    corpus = " ".join(p.text for p in payloads)
    placed: list[dict[str, str]] = []
    for hypothesis in finding.get("hypotheses", []):
        for ref in list(hypothesis.get("supporting", ())) + list(
            hypothesis.get("contradicting", ())
        ):
            if ref.get("span") is None:
                continue
            ref["span"] = f"{ref['span']} {corpus}"
            placed.append({"field": "span", "event_id": str(ref.get("event_id"))})

    # The narrative is the other free-text field an operator reads, and it is on the detail screen
    # itself rather than behind the drawer, so it carries the corpus too.
    finding["narrative"] = f"{finding.get('narrative', '')} {corpus}"
    placed.append({"field": "narrative", "event_id": "-"})

    target.write_text(json.dumps(finding, indent=2) + "\n", encoding="utf-8")
    record = {
        "experiment_id": experiment_id(payloads),
        "generated": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
        "artifact": target.name,
        "fields_injected": placed,
        "markers": [p.marker for p in payloads],
        "payload_count": len(payloads),
        "spans_available": spans_in(finding),
    }
    (destination / "injection_record.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--inject-all",
        action="store_true",
        help="use the whole corpus rather than only the classes a browser interprets",
    )
    args = parser.parse_args(argv)

    payloads = ALL_PAYLOADS if args.inject_all else rendered_payloads()
    root = Path(tempfile.mkdtemp(prefix="volve-injected-"))
    record = inject(args.cache, root, payloads)

    # Imported here so the store dependency is overridden before the first request, and so this
    # script can be imported for its `inject` without starting a server.
    from api.main import app, get_log, get_store

    app.dependency_overrides[get_store] = lambda: RunStore(
        cache=root, traces=root / "investigations"
    )
    app.dependency_overrides[get_log] = lambda: ReviewLog(path=root / "review_log.jsonl")

    print(f"experiment  {record['experiment_id']}")
    print(f"artifacts   {root}")
    print(
        f"injected    {record['payload_count']} payloads into "
        f"{len(record['fields_injected'])} fields of {record['artifact']}"
    )
    for placed in record["fields_injected"]:
        print(f"  {placed['field']:<10} {placed['event_id']}")
    print(f"serving     http://127.0.0.1:{args.port}/")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
