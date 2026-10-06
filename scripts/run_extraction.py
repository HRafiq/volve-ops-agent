"""Extract NPT events, store a version, build the index, and draw the labelling sample.

The committed entry point behind the extraction layer's figures, for the same reason Phase 1
has one: a result that cannot be regenerated from the repository is not a result.

    python scripts/run_extraction.py data/cache/ddr_xml --store data/cache/npt_store
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any

from volve_ops.extraction.baselines import echo_state_detail, echo_subcategory
from volve_ops.extraction.npt import extract_from_directory
from volve_ops.extraction.sampling import draw_sample
from volve_ops.extraction.store import EventStore
from volve_ops.retrieval.index import BM25Index, chunks_from_events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("--store", type=Path, default=Path("data/cache/npt_store"))
    parser.add_argument("--version", default="extractor-v0")
    parser.add_argument("--manifest", type=Path, default=Path("data/cache/extraction_run.json"))
    args = parser.parse_args(argv)

    reports = sorted(args.report_dir.glob("*.xml"))
    events = extract_from_directory(args.report_dir)
    print(f"reports {len(reports)}; non-productive events {len(events)}")
    print(f"  wells {len({e.well for e in events})}, wellbores {len({e.wellbore for e in events})}")
    print(f"  total non-productive time {sum(e.duration_hours for e in events):,.0f} hours")

    heads = collections.Counter(e.category for e in events)
    print(f"  by activity head: {dict(heads)}")

    store = EventStore(args.store)
    if args.version in store.versions():
        print(f"  store version {args.version!r} exists; verifying rather than rewriting")
        store.verify(args.version)
        manifest = store.manifest(args.version)
    else:
        manifest = store.write(
            events,
            version=args.version,
            source_directory=args.report_dir,
            source_file_count=len(reports),
        )
        print(f"  wrote store version {manifest.version}")
    print(f"  content hash {manifest.content_hash[:16]}")

    index = BM25Index(chunks_from_events(events))
    print(f"\nindexed {len(index)} narrative chunks")

    for name, fn in (
        ("echo-subcategory", echo_subcategory),
        ("echo-statedetail", echo_state_detail),
    ):
        counts = collections.Counter(fn(e).value for e in events)
        stated = sum(v for k, v in counts.items() if k != "not_stated")
        print(
            f"  baseline {name}: attributes on {stated}/{len(events)} = {stated / len(events):.0%}"
        )

    development = draw_sample(events)
    hold_out = draw_sample(events, split="hold-out")
    print(f"\nlabelling sample: development {development.drawn} of {development.eligible} eligible")
    print(f"                  hold-out    {hold_out.drawn} of {hold_out.eligible} eligible")

    payload: dict[str, Any] = {
        "reports": len(reports),
        "events": len(events),
        "store_version": manifest.version,
        "content_hash": manifest.content_hash,
        "parser_version": manifest.parser_version,
        "extractor_version": manifest.extractor_version,
        "protocol_version": "v2",
        "indexed_chunks": len(index),
        "development_sample": development.model_dump(mode="json"),
        "hold_out_sample": hold_out.model_dump(mode="json"),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nrun manifest written to {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
