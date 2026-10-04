# volve-ops-agent

Evidence-bound AI agents for oil and gas operational investigation using Equinor's Volve
dataset, deterministic analytics, provenance-tracked reasoning, calibrated abstention, and
human review.

## Status

Pre-registration. No data has been retrieved yet, and no results exist.

This repository's first commit of substance is the evaluation protocol, pushed before any
dataset file was retrieved or opened. That ordering is the point: every threshold the
project will later be judged against was fixed while its author had not seen the data, so
those criteria can fail honestly.

- [`docs/eval_protocol.md`](docs/eval_protocol.md) sets out how the system will be judged:
  the two feasibility criteria, what counts as a valid producing day, expectation-engine
  pass marks measured against named naive baselines, episode criteria, the temporal split
  and frozen hold-out, and leakage rules. It states what it defers and why, and the rules
  under which it may be amended.
- [`docs/data_manifest.md`](docs/data_manifest.md) is the record of what data the results
  rest on. Raw and processed data are never committed; the manifest carries sources, sizes,
  checksums and licence terms instead. Its tables are empty until retrieval.
- [`docs/architecture_decisions/`](docs/architecture_decisions/) holds the decisions and
  the reasoning behind them.

Results, limitations and reproduction instructions are added as the work produces them. A
figure appears here only when a run has produced it.

## Scope and boundaries

Nothing here touches equipment. The system reads data, reaches conclusions, and hands them
to a person; there is no actuation path and no automated action of any kind. That keeps the
risk surface small and leaves decision authority where it belongs, which is a design choice
rather than a claim to meet any formal operator safety case.

Public data only. The dataset is Equinor's Volve open dataset, used under its own licence,
recorded in the data manifest. Nothing here implies Equinor endorsement.

## Licence

Code is MIT licensed; see [LICENSE](LICENSE). The source dataset carries its own separate
terms, recorded in the data manifest at retrieval.
