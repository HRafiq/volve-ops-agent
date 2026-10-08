"""Score the labelled development sample: section 14.3's pass marks, then the two baselines.

The committed entry point behind every figure in docs/labelling_results.md.

    python scripts/run_label_scoring.py labels/development_pass1.jsonl \
        --store data/cache/npt_store --reports data/cache/ddr_xml

Protocol section 17 governs what the output may claim. The baseline figures are reported; no
approach is selected against these labels, and the script says so rather than leaving the reader
to remember it.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any

from volve_ops.extraction.baselines import echo_state_detail, echo_subcategory
from volve_ops.extraction.integrity import check_reports
from volve_ops.extraction.labels import join_to_events, read_label_file
from volve_ops.extraction.npt import CauseLabel
from volve_ops.extraction.scoring import (
    LabelSource,
    score_macro,
    selection_permitted,
)
from volve_ops.extraction.store import EventStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path)
    parser.add_argument("--store", type=Path, default=Path("data/cache/npt_store"))
    parser.add_argument("--version", default="extractor-v0")
    parser.add_argument("--reports", type=Path, default=Path("data/cache/ddr_xml"))
    parser.add_argument("--manifest", type=Path, default=Path("data/cache/label_scoring_run.json"))
    args = parser.parse_args(argv)

    events = {e.event_id: e for e in EventStore(args.store).read(args.version)}
    rows = read_label_file(args.labels)
    labelled, spans = join_to_events(rows, events.values())
    sample = [events[e.event_id] for e in labelled]

    sources = collections.Counter(e.label_source.value for e in labelled)
    print(f"labels {len(labelled)}; provenance {dict(sources)}")
    permitted = selection_permitted(labelled)
    print(f"selection permitted by protocol section 17.2: {permitted}")
    if not permitted:
        print("  baseline figures below are reported, not gates. No approach is selected.")

    # Section 14.3, both pass marks. Unaffected by label provenance.
    #
    # Checked over every qualifying block in the documents the labelled sample came from, not only
    # the 135 sampled blocks. That is a superset of what the pass mark asks for, and the wider set
    # is what catches a block the parser dropped: a dropped block is never in the sample, because
    # the sample is drawn from what the parser emitted.
    names = {e.source_document for e in sample}
    documents = sorted({args.reports / name for name in names})
    in_scope = [e for e in events.values() if e.source_document in names]
    integrity = check_reports(documents, in_scope)
    print(
        f"\nsection 14.3 over {integrity.documents} documents of the labelled sample: "
        f"{integrity.qualifying_blocks} qualifying blocks, {integrity.events_checked} events"
    )
    print(f"  detection exact: {integrity.detection_exact}")
    print(f"  duration exact:  {integrity.duration_exact}")
    for finding in integrity.findings[:10]:
        print(f"  ! {finding.kind}: {finding.source_document}: {finding.detail}")

    # Section 14.5, reported.
    #
    # Every class in the taxonomy appears, zeros included. A `Counter` omits what it never saw, so
    # the three classes with no label were absent from the manifest and their table rows rendered as
    # "not produced" when the honest value is 0. A zero here is a result and not a gap: two of the
    # three are unreachable under the labelling guide's first precedence rule, which is why section
    # 14.5's selection gate is suspended, and that argument needs the zero to be published.
    gold = [e.cause for e in labelled]
    counted = collections.Counter(c.value for c in gold)
    distribution = {label.value: counted.get(label.value, 0) for label in CauseLabel}
    stated = sum(1 for c in gold if c is not CauseLabel.NOT_STATED)
    print(f"\nlabel distribution over {len(gold)} events, {stated} with a stated cause:")
    for name, count in sorted(distribution.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {count:>4}  {name}")

    scores: dict[str, Any] = {}
    for name, fn in (
        ("echo-subcategory", echo_subcategory),
        ("echo-statedetail", echo_state_detail),
    ):
        predicted = [fn(e) for e in sample]
        macro = score_macro(gold, predicted)
        exact = sum(1 for g, p in zip(gold, predicted, strict=True) if g is p)
        print(
            f"\nbaseline {name}: macro-F1 {macro.macro_f1:.4f} over "
            f"{macro.classes_in_average} classes; exact agreement {exact}/{len(gold)} "
            f"= {exact / len(gold):.1%}"
        )
        for row in macro.per_class:
            mark = "*" if row.in_macro_average else " "
            print(
                f"  {mark} {row.label.value:<23} n={row.support:<3} "
                f"P={row.precision:.3f} R={row.recall:.3f} F1={row.f1:.3f}"
            )
        scores[name] = {
            "macro_f1": macro.macro_f1,
            "classes_in_average": macro.classes_in_average,
            "exact_agreement": exact / len(gold),
            "per_class": [row.model_dump(mode="json") for row in macro.per_class],
        }

    first = [echo_subcategory(e) for e in sample]
    second = [echo_state_detail(e) for e in sample]
    consensus = [(g, a) for g, a, b in zip(gold, first, second, strict=True) if a is b]
    agree_with_consensus = sum(1 for g, a in consensus if g is a)
    print(
        f"\nthe two baselines agree with each other on {len(consensus)}/{len(gold)} events; "
        f"the labels match that consensus on {agree_with_consensus}/{len(consensus)}"
    )

    # Split the consensus two ways, because the two halves say different things and an aggregate
    # over them says neither. Where both tables abstain, a label naming a cause is the behaviour
    # the labels are supposed to have. Where both name a cause, a disagreement is a contradiction.
    abstained = [(g, x) for g, x in consensus if x is CauseLabel.NOT_STATED]
    asserted = [(g, x) for g, x in consensus if x is not CauseLabel.NOT_STATED]
    print(
        f"  consensus is not_stated on {len(abstained)}; the labels name a cause on "
        f"{sum(1 for g, _ in abstained if g is not CauseLabel.NOT_STATED)}"
    )
    print(
        f"  consensus names a cause on {len(asserted)}; the labels agree on "
        f"{sum(1 for g, x in asserted if g is x)}, and call "
        f"{sum(1 for g, _ in asserted if g is CauseLabel.NOT_STATED)} of them not_stated"
    )
    shapes = collections.Counter(
        (e.subcategory, e.state_detail)
        for (_, _), e in zip(
            asserted,
            [
                e
                for e, a, b in zip(sample, first, second, strict=True)
                if a is b and a is not CauseLabel.NOT_STATED
            ],
            strict=True,
        )
    )
    for (subcategory, detail), count in shapes.most_common():
        print(f"    {count:>3}  {subcategory!r} filed with detail state {detail!r}")

    # Section 14.6's data-quality statistic. Judgement-based: the criterion is in the labelling
    # guide and applying it needs a reading of the comment, so the mechanical companion below is
    # reported beside it rather than instead of it.
    miscoded = sum(1 for r in rows if r.get("source_coding_looks_wrong"))
    print(f"\nsource coding flagged as disagreeing with the comment: {miscoded}/{len(rows)}")
    mechanical = sum(
        1 for g, p in zip(gold, first, strict=True) if p is not CauseLabel.NOT_STATED and g is not p
    )
    print(
        f"  mechanical companion, needing no judgement: echo-subcategory names a cause that is "
        f"not the label on {mechanical}/{len(gold)} = {mechanical / len(gold):.1%}"
    )

    rules = collections.Counter(str(r.get("applied_rule")) for r in rows)
    print("\napplied rule:")
    for rule, count in rules.most_common():
        print(f"  {count:>4}  {rule}")

    taxonomy = {c.value for c in CauseLabel}
    noted = [r for r in rows if r.get("cause_notes")]
    alternatives = [
        r
        for r in noted
        if any(name in str(r["cause_notes"]) and name != r["cause"] for name in taxonomy)
    ]
    print(
        f"\nrows carrying a note: {len(noted)}; of those, {len(alternatives)} name a taxonomy "
        f"label other than the one assigned"
    )

    spans_present = sum(1 for v in spans.values() if v is not None)
    print(f"spans cited: {spans_present}; all verified as verbatim substrings on read")

    payload: dict[str, Any] = {
        "protocol_version": "v3",
        "labels": str(args.labels),
        "label_count": len(labelled),
        "label_provenance": dict(sources),
        "selection_permitted": permitted,
        "expert_labels": sources.get(LabelSource.EXPERT.value, 0),
        "section_14_3": {
            "documents": integrity.documents,
            "qualifying_blocks": integrity.qualifying_blocks,
            "events_checked": integrity.events_checked,
            "detection_exact": integrity.detection_exact,
            "duration_exact": integrity.duration_exact,
            "findings": [f.model_dump(mode="json") for f in integrity.findings],
        },
        "label_distribution": distribution,
        "stated_cause_events": stated,
        "baselines": scores,
        "baseline_mutual_agreement": len(consensus) / len(gold),
        "labels_match_baseline_consensus": (
            agree_with_consensus / len(consensus) if consensus else 0.0
        ),
        "source_coding_flagged": miscoded,
        "source_coding_flagged_rate": miscoded / len(rows),
        "subcategory_names_a_cause_that_is_not_the_label": mechanical / len(gold),
        "baseline_consensus_abstained": len(abstained),
        "baseline_consensus_abstained_labels_name_a_cause": sum(
            1 for g, _ in abstained if g is not CauseLabel.NOT_STATED
        ),
        "baseline_consensus_asserted": len(asserted),
        "baseline_consensus_asserted_labels_agree": sum(1 for g, x in asserted if g is x),
        "applied_rule": dict(rules),
        "rows_with_a_note": len(noted),
        "rows_naming_another_label_in_the_note": len(alternatives),
        "spans_cited": spans_present,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nrun manifest written to {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
