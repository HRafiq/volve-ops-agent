"""Draw protocol section 17.4's 40-event expert adjudication subsample, blind.

    python scripts/draw_adjudication.py labels/development_pass1.jsonl --out adjudication/

Writes two files. The worksheet is what an adjudicator works from, and it carries exactly protocol
section 14.2's permitted set: the comment, the activity code, the state and detail state, and the
timestamps. No machine label, no span, no applied rule, no baseline prediction, and not the wellbore
identifier that the machine labelling pass saw.

Field-level blinding is not the whole of blinding. The adjudicator also reads the labelling guide,
whose conventions section describes how the first pass resolved several of these events. Section
17.4 names which version of the guide an adjudicator is given. This script cannot enforce that.

The draw record carries the seed, the strata sizes and the drawn ids, so the draw can be checked
as the specified one rather than taken on trust. It is separate from the worksheet so the
worksheet can be handed over without handing over the stratification.

Scoring the returned adjudication is not this script's job and is deliberately left until there is
something to score; protocol section 17.4 fixes the threshold at 80 percent agreement and what
happens either side of it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from volve_ops.extraction.adjudication import CONTESTED, draw_adjudication_sample
from volve_ops.extraction.labels import join_to_events, read_label_file
from volve_ops.extraction.store import EventStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path)
    parser.add_argument("--store", type=Path, default=Path("data/cache/npt_store"))
    parser.add_argument("--version", default="extractor-v0")
    parser.add_argument("--out", type=Path, default=Path("data/cache/adjudication"))
    args = parser.parse_args(argv)

    events = list(EventStore(args.store).read(args.version))
    labelled, _ = join_to_events(read_label_file(args.labels), events)
    draw = draw_adjudication_sample({e.event_id: e.cause for e in labelled}, events)

    print(f"drew {draw.size} of {draw.eligible} labelled events at seed {draw.seed}")
    print(f"  {draw.from_contested_classes} from {sorted(c.value for c in CONTESTED)}")
    print(f"  {draw.from_the_rest} at random from the rest")

    args.out.mkdir(parents=True, exist_ok=True)
    worksheet = args.out / "worksheet.jsonl"
    with worksheet.open("w", encoding="utf-8") as handle:
        for item in draw.items:
            handle.write(json.dumps(item.model_dump(mode="json")) + "\n")

    record = args.out / "draw.json"
    record.write_text(
        json.dumps(
            {
                "size": draw.size,
                "seed": draw.seed,
                "eligible": draw.eligible,
                "from_contested_classes": draw.from_contested_classes,
                "from_the_rest": draw.from_the_rest,
                "event_ids": list(draw.event_ids),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nblind worksheet: {worksheet}")
    print(f"draw record:     {record}")
    print("\nThe worksheet carries no machine label and no baseline prediction. Keep it that way.")
    print("Give the adjudicator the protocol section 17.4 guide version, not the current one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
