"""A terminal tool for labelling NPT causes, following docs/labelling_guide.md.

The guide is the specification; this enforces the parts a tool can. It shows the labeller
exactly what the model will be given and nothing else, it takes the evidence span as a literal
substring and refuses one that is not, and it saves after every event so a session can be
stopped and resumed without losing work.

    python scripts/label_npt.py data/cache/npt_store extractor-v0 --out data/cache/labels

Pass one is the label set. The guide reserves pass two for estimating agreement and says it
must never overwrite pass one, so the tool writes passes to separate files and refuses to mix
them.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from volve_ops.extraction.npt import CauseLabel, NPTEvent
from volve_ops.extraction.sampling import draw_sample
from volve_ops.extraction.store import EventStore

CHOICES: Sequence[CauseLabel] = tuple(CauseLabel)


def _show(event: NPTEvent, position: int, total: int) -> None:
    print("\n" + "=" * 78)
    print(
        f"[{position}/{total}]  {event.wellbore}   {event.report_date}   "
        f"{event.duration_hours:.2f} h"
    )
    print(f"code: {event.activity_code}    state: {event.state} / {event.state_detail or '-'}")
    print("-" * 78)
    print(event.comment or "(no comment)")
    print("-" * 78)
    for index, label in enumerate(CHOICES, start=1):
        print(f"  {index:>2}  {label.value}")
    print("   s  skip for now      q  save and quit")


def _prompt_cause() -> CauseLabel | str:
    while True:
        raw = input("cause> ").strip().lower()
        if raw in {"s", "q"}:
            return raw
        if raw.isdigit() and 1 <= int(raw) <= len(CHOICES):
            return CHOICES[int(raw) - 1]
        match = [c for c in CHOICES if c.value.startswith(raw)] if raw else []
        if len(match) == 1:
            return match[0]
        print("  pick a number, or type enough of a label to be unambiguous")


def _prompt_span(comment: str, cause: CauseLabel) -> str | None:
    """Take a span and refuse one that is not literally in the comment.

    The guide is explicit that a span is a verbatim substring, and that a cause without a span
    is the thing this project exists to prevent. Checking here rather than at scoring time means
    the labeller fixes it while looking at the text.
    """
    if cause is CauseLabel.NOT_STATED:
        return None
    while True:
        raw = input("span (verbatim; blank if the comment states no cause)> ").strip()
        if not raw:
            return None
        if raw in comment:
            return raw
        print("  that is not a substring of the comment; copy it exactly, or trim it")
        print("  or leave it blank, which records the cause as not stated")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store", type=Path)
    parser.add_argument("version")
    parser.add_argument("--out", type=Path, default=Path("data/cache/labels"))
    parser.add_argument("--split", default="development", choices=["development", "hold-out"])
    parser.add_argument("--pass", dest="label_pass", type=int, default=1, choices=[1, 2])
    args = parser.parse_args(argv)

    events = {e.event_id: e for e in EventStore(args.store).read(args.version)}
    sample = draw_sample(list(events.values()), split=args.split)
    chosen = [events[i] for i in sample.event_ids]

    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / f"{args.split}_pass{args.label_pass}.jsonl"

    done: dict[str, dict[str, object]] = {}
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[str(row["event_id"])] = row
        print(f"resuming: {len(done)} of {len(chosen)} already labelled in {target.name}")

    remaining = [e for e in chosen if e.event_id not in done]
    if not remaining:
        print(f"nothing left to label for {args.split} pass {args.label_pass}")
        return 0

    print(f"{len(remaining)} events to label. Read only what is shown; the guide explains why.")
    for position, event in enumerate(remaining, start=len(done) + 1):
        _show(event, position, len(chosen))
        cause = _prompt_cause()
        if cause == "q":
            break
        if cause == "s":
            continue
        assert isinstance(cause, CauseLabel)
        span = _prompt_span(event.comment, cause)
        if span is None and cause is not CauseLabel.NOT_STATED:
            print("  no span given, so the cause is not stated by the comment; recording that")
            cause = CauseLabel.NOT_STATED
        note = input("note (optional)> ").strip()
        disagrees = input("does the source's own coding look wrong? [y/N]> ").strip().lower()

        # Every field docs/labelling_guide.md fixes. The source document, activity code and
        # state are carried so a label can be audited without re-joining the store, and
        # labelled_at is the only thing the guide's "at least a week later" rule for pass two
        # could ever be checked against.
        row = {
            "event_id": event.event_id,
            "source_document": event.source_document,
            "activity_code": event.activity_code,
            "state": event.state,
            "cause": cause.value,
            "evidence_span": span,
            "cause_notes": note or None,
            "source_coding_looks_wrong": disagrees == "y",
            "labeller_pass": args.label_pass,
            "labelled_at": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
        }
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
        done[event.event_id] = row

    print(f"\n{len(done)} of {len(chosen)} labelled; written to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
