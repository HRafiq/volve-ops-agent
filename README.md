# volve-ops-agent

Evidence-bound AI agents for oil and gas operational investigation using Equinor's Volve
dataset, deterministic analytics, provenance-tracked reasoning, calibrated abstention, and
human review.

## Status

Data profiled, both feasibility criteria executed, the deterministic expectation and episode
layer built and measured, and drilling-report extraction running. No agent exists yet, and no
cause attribution: that is pre-registered and waiting on hand labels.

The evaluation protocol was pushed before any dataset file was retrieved. That ordering is the
point: every threshold the project will be judged against was fixed while its author had not
seen the data, so those criteria could fail honestly. Two of them did.

- [`docs/eval_protocol.md`](docs/eval_protocol.md) sets out how the system will be judged: the
  two feasibility criteria, what counts as a valid producing day, expectation-engine pass marks
  measured against named naive baselines, episode criteria, the temporal split and frozen
  hold-out, and leakage rules.
- [`docs/data_profile.md`](docs/data_profile.md) is what the data turned out to be: six oil
  producers, 7,893 valid producing days, 1,759 daily drilling reports, and the coverage gaps
  that limit what can be claimed from them.
- [`docs/data_manifest.md`](docs/data_manifest.md) records every file read, with checksums.
  Raw and processed data are never committed.
- [`docs/expectation_results.md`](docs/expectation_results.md) is the measured performance of
  the expectation engine on development data, the model comparison with the pre-registered
  selection rule applied, and the failure modes that showed up while building it.
- [`docs/extraction_results.md`](docs/extraction_results.md) is the drilling-report extraction:
  3,673 non-productive events over 11 wells, what the two fixed baselines predict, and why both
  are named.
- [`docs/labelling_guide.md`](docs/labelling_guide.md) is the labelling specification, written
  before any label was made.
- [`docs/architecture_decisions/`](docs/architecture_decisions/) holds the decisions and the
  reasoning, including both feasibility results.

The deterministic layer is reachable three ways, all over the same services. `src/volve_ops/domain/`
holds the engine; `src/volve_ops/tools/` wraps it in typed, bounded tools that refuse an
over-large request rather than truncating it; and `src/volve_ops/mcp_server/` exposes those
tools over MCP as an optional extra. The adapter decides nothing, which is the point: a rule
about what a caller may ask for lives in the tool layer, once.

Alongside it, `src/volve_ops/extraction/` turns the drilling reports into typed non-productive
events in a versioned store, `src/volve_ops/retrieval/` indexes their narrative lexically, and
`src/volve_ops/provenance/` holds the fact ledger that refuses a derived value whose inputs it
does not have. Two committed scripts regenerate the published figures:
`scripts/run_expectation_study.py` and `scripts/run_extraction.py`, each writing a run manifest.

### Feasibility results

Drilling plan reconstruction **fails**. The dataset does contain eighteen drilling programmes,
but only two wells have plans covering enough of their drilling history to compare against, and
three were required. Recorded time is therefore reported as non-NPT recorded time, NPT and
other unclassified time, with no invented planning baseline. See
[ADR 0003](docs/architecture_decisions/0003-b1-drilling-plan-reconstruction.md).

Allocation reconciliation **fails**. The production data is per-wellbore at two levels of
aggregation, with no independently derived series to reconcile against. See
[ADR 0004](docs/architecture_decisions/0004-c1-allocation-reconciliation.md).

Both were pre-registered before the data was seen, and the first was predicted to fail for a
reason that turned out to be wrong. It fails on coverage, not on availability.

### Expectation engine

No candidate model clears the pre-registered bar. The requirement was to beat the better of two
named naive baselines by 10 percent relative WAPE at three horizons; the best candidate clears it
at the two shorter horizons, by 18.7 and 11.6 percent, and loses by 1.9 percent at the longest. The protocol's fallback therefore
applies and `naive-median28` becomes the expectation model, deliberately not the
better-scoring persistence baseline, which cannot detect sustained underperformance by
construction. Calibration fails on both qualifying wells and the interval construction is the
cause. Details and the full comparison are in the results document.

Results, limitations and reproduction instructions grow as the work produces them. A figure
appears here only when a run has produced it.

## Scope and boundaries

Nothing here touches equipment. The system reads data, reaches conclusions, and hands them
to a person; there is no actuation path and no automated action of any kind. That keeps the
risk surface small and leaves decision authority where it belongs, which is a design choice
rather than a claim to meet any formal operator safety case.

Public data only. The dataset is Equinor's Volve open dataset, used under its own licence,
recorded in the data manifest. Nothing here implies Equinor endorsement.

## Licence

Code is MIT licensed; see [LICENSE](LICENSE). The source dataset carries its own separate terms:
see [DATA_LICENSE.md](DATA_LICENSE.md) and [NOTICE-VOLVE.md](NOTICE-VOLVE.md).
