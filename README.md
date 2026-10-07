# volve-ops-agent

Can an AI system investigate why an oil well underperformed, and be held to the same evidence
standard as a person writing the same report?

This is an evidence-bound investigation system over Equinor's Volve open dataset. Every threshold it
is judged against was written down and pushed before the run it judges, so the criteria could fail
honestly. Several did, and this README says which.

## Where the project is

| Phase | What it delivers | Status |
|---|---|---|
| 0 | Data profile, licence, domain, and the two feasibility criteria | **complete** |
| 1 | Expectation engine, episode detector, domain services | **complete** |
| 2 | Drilling-report extraction, lexical retrieval, cause labels | **complete** |
| 3 | Agent A: bounded investigation controller with a provenance gate | **complete** |
| 4 | Evaluation harness: version freeze, leakage audit, results table | **complete** |
| 5 | Agent B: NPT post-mortem and the corrections register | **next** |
| 6 | Operator console | not started |
| 7 | Failure, health and security experiments | not started |
| 8 | Frozen hold-out scored once, public write-up | not started |

The hold-out has never been scored and never been looked at. Phase 4's leakage audit exists to prove
that mechanically rather than assert it, and it gates the build.

118 tracked files, 511 tests, ruff and mypy strict clean. No model is called by any layer yet: every
component runs deterministically, which is what makes it testable.

## What the data refused to support

Three capabilities were pre-registered and the dataset declined all three, for one reason: Volve is
generous about measurements and thin about the operational record that explains them.

| Pre-registered capability | Outcome | Why |
|---|---|---|
| Planned-versus-actual drilling time | **fails** | 18 drilling programmes exist, but only 2 wells have plans covering enough of their history. 3 were required. [ADR 0003](docs/architecture_decisions/0003-b1-drilling-plan-reconstruction.md) |
| Allocation reconciliation | **fails** | Production is per-wellbore at two aggregation levels, with no independent series to reconcile against. [ADR 0004](docs/architecture_decisions/0004-c1-allocation-reconciliation.md) |
| Documented root cause for a production episode | **rare, 1 of 14** | Not one of 3,673 drilling-report events falls inside any episode window. Reports are written when a rig is on the well, and a producing well has no rig. [ADR 0008](docs/architecture_decisions/0008-drilling-reports-rarely-overlap-production-episodes.md) |

The first was predicted to fail for a reason that turned out to be wrong. It fails on coverage, not
availability.

## Results

**Expectation engine.** No candidate model clears the pre-registered bar of beating the better naive
baseline by 10 percent relative WAPE at three horizons. The best clears it at 7 and 14 days, by 18.7
and 11.6 percent, and loses by 1.9 percent at 28. The protocol's fallback therefore applies and
`naive-median28` becomes the expectation model, deliberately not the better-scoring persistence
baseline, which cannot detect sustained underperformance by construction. Calibration fails by 2 to 4
times on both qualifying wells. [Details](docs/expectation_results.md)

**Cause labels.** 135 labels over drilling-report events, and they are **machine-assisted**: produced
by a language model applying a guide written beforehand, not by a domain expert. I have no
drilling-operations experience and cannot say whether a 1997 comment describes an equipment failure or
a hole condition. That cost a pass mark, which is the honest outcome rather than a workaround.

| Figure | Value |
|---|---|
| Labels, all machine-assisted | 135 |
| `not_stated`, the load-bearing label | 75 of 135, 55.6 percent |
| `echo-statedetail` baseline macro-F1 | 0.3329 |
| `echo-subcategory` baseline macro-F1 | 0.2992 |
| Source subcategory contradicting its own comment | 12 of 135, 8.9 percent |

Protocol section 17 suspends the cause-attribution selection gate: an extraction model scored against
model labels is compared with a labeller of its own kind. The code enforces that, not just the prose.
[Details](docs/labelling_results.md)

**Investigation layer.** All five pre-registered gates pass over all 14 detected episodes.

| Figure | Value |
|---|---|
| Verdicts | 7 supported, 4 insufficient evidence, 3 multiple plausible |
| Document citations across all findings | 2 |
| Findings reaching a documented root cause | 1 |
| Agreement with the fixed baseline on the driver | 5 of the 7 where both named one |

The one documented root cause cites a report dated the day before onset: "Closed in well to prepare
for handover." Three episodes stop on missing evidence rather than guessing, because `15/9-F-12` has
usable downhole pressure on 31.2 percent of its producer rows where counting non-empty cells reports
99.8. [Details](docs/investigation_results.md)

## The three things I learned

**A check written in the same breath as the thing it checks tends to test that thing against itself.**
This happened in four consecutive phases. The worst case was a leakage audit whose central check
tested whether a fitted day fell outside the development window, over a day set it had built with the
same filter. An independent review made the expectation study fit on the whole record and the audit
reported clean. The fix was structural: the scripts record the dates they actually fitted on, and the
audit reads those. Reproducing the same leak now yields 5,108 out-of-window dates across six wells and
a failed build. A check cannot audit another script's filtering by re-deriving it.

**A correct table can carry a wrong conclusion, and arithmetic review will pass it.** I published that
the top causal level was unreachable "for want of documents rather than capability", backed by event
counts that all verified. Both halves were wrong: the level was never implemented in any code path,
and retrieval was querying the wrong hypothesis on the one episode where documents existed. When a
result conveniently blames the data for something your own code is causing, check the code first.

**Missingness that a presence check cannot see is the most expensive kind.** Two channels in the
production workbook record `0.00` when the gauge is not reporting: 2,312 rows, 1,924 of them while the
well was flowing. Counting non-empty cells says `15/9-F-12` has downhole pressure on 99.8 percent of
its days. Treating the zeros as the absences they are gives 31.2 percent, and that well carries 9 of
the 14 episodes.

## Limitations a reader should carry

The cause labels are not expert labels, and no correctness figure is reported anywhere in this
project. Scoring whether a choke reduction explains a shortfall on a specific North Sea well needs a
reader I do not have. Protocol sections 17, 18 and 19 each say so, and section 17.4 fixes the
adjudication that would settle it: 40 events, blind, 80 percent agreement.

Nine metrics the plan asked for are deferred, each with its obstacle named in
[`docs/results_table.md`](docs/results_table.md) beside the 119 figures that do exist. Every obstacle
is one of three things: the dataset lacks what the metric needs, the sample is too small for the
number to mean anything, or there is no domain reader. The third appears four times.

14 episodes from one detector on two wells is not a benchmark, and the protocol declines to
manufacture precision from it.

## How it is put together

`src/volve_ops/domain/` holds the deterministic engine. `src/volve_ops/tools/` wraps it in typed,
bounded tools that refuse an over-large request rather than truncating it, and
`src/volve_ops/mcp_server/` exposes those over MCP as an optional extra. The adapter decides nothing,
which is the point: a rule about what a caller may ask for lives in the tool layer, once.

`extraction/` turns drilling reports into typed events in a versioned store, `retrieval/` indexes
their narrative lexically, `provenance/` holds a fact ledger that refuses a derived value whose inputs
it does not have, `investigation/` is the bounded controller, and `evaluation/` is the harness that
judges the project's own account of itself.

## Reproduce

Each script writes a run manifest, and a figure without one is not reported as a result.

```bash
python scripts/run_expectation_study.py "data/cache/Volve production data.xlsx" data/cache/ddr_xml
python scripts/run_extraction.py data/cache/ddr_xml
python scripts/run_label_scoring.py labels/development_pass1.jsonl
python scripts/run_investigations.py "data/cache/Volve production data.xlsx" data/cache/ddr_xml
python scripts/run_evaluation.py "data/cache/Volve production data.xlsx" data/cache/ddr_xml
```

The last one is the gate: it exits non-zero on a leakage finding or an unreported figure. Raw and
processed data are never committed; [`docs/data_manifest.md`](docs/data_manifest.md) records every
file read with checksums, and the one exception is recorded there too.

CI is split so money cannot be spent by accident. No workflow an event can start may read a secret,
checked by parsing every workflow file. Anything that would call a model is manual only.

## Documents

| Document | What it is |
|---|---|
| [`docs/eval_protocol.md`](docs/eval_protocol.md) | The pre-registration. Its commit history is the evidence, tagged `prereg-v0` through `prereg-v8` |
| [`docs/data_profile.md`](docs/data_profile.md) | What the data turned out to be, and the coverage gaps that limit what can be claimed |
| [`docs/results_table.md`](docs/results_table.md) | Every figure in the project, with its denominator and whether it is gated, reported or deferred |
| [`docs/architecture_decisions/`](docs/architecture_decisions/) | Eight decisions, including all three feasibility outcomes |
| [`labels/development_pass1.jsonl`](labels/development_pass1.jsonl) | The label set itself, each row with its provenance, span and the rule that settled it |

## Scope and boundaries

Nothing here touches equipment. The system reads data, reaches conclusions, and hands them to a
person. There is no actuation path and no automated action of any kind. That keeps the risk surface
small and leaves decision authority where it belongs, which is a design choice rather than a claim to
meet any formal operator safety case.

Public data only. The dataset is Equinor's Volve open dataset, used under its own licence and recorded
in the data manifest. Nothing here implies Equinor endorsement.

## Licence

Code is MIT licensed; see [LICENSE](LICENSE). The source dataset carries its own separate terms: see
[DATA_LICENSE.md](DATA_LICENSE.md) and [NOTICE-VOLVE.md](NOTICE-VOLVE.md).
