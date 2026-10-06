# Evaluation results: the harness, the leakage audit, and what this project cannot measure

Regenerate with
`python scripts/run_evaluation.py "data/cache/Volve production data.xlsx" data/cache/ddr_xml --table docs/results_table.md`.
Its exit status is the gate, so a leakage finding or an uncovered figure fails the build rather than
printing and passing. It calls no model.

Protocol section 19 fixed all of this before the harness existed and was pushed as `prereg-v6`. Unlike
section 18 it states its own thresholds, which is the lesson amendment 4 had to record afterwards.

The consolidated table is [`results_table.md`](results_table.md): 56 rows, every one carrying its
denominator, its status, and for a deferred row what would settle it.

## The six gating pass marks

| section 19 pass mark | result | what it examined |
|---|---|---|
| 19.1 every version field present | **pass** | 9 fields, none blank, absence recorded as `none` |
| 19.1 manifest hash reproduces | **pass** | identical across repeated runs |
| 19.2 leakage audit clean | **pass** | 4,770 fitted days, 135 labels, 7 wells, 2 investigated wells |
| 19.3 every manifest figure has a table row | **pass** | 0 uncovered of all four run manifests |
| 19.5 no mechanical false root-cause claim | **pass** | 1 documented claim examined |
| 19.7 no repeated identical tool call | **pass** | 14 traces, 30 retrieval queries |

The third column is the habit this project had to learn twice. Phase 2 published a pass mark that
compared a value against its own definition, and Phase 3 published one whose test had been written so
it could not fail. Every gate here has a test that makes it fail, and every check reports how much it
examined, so a gate that passed over nothing is visible as such. One does:
`correction_from_the_hold_out` examined zero, because no correction store exists yet, and the harness
prints it under "checks that examined nothing" rather than counting it as a clean result.

## The version freeze

```
dataset_version          workbook sha256 514d4e38763e09be, 1759 reports
label_set_version        development_pass1.jsonl n=135 provenance=machine_assisted
parser_version           ingest-v0
extractor_version        extractor-v0
investigator_version     investigator-v0
retrieval_index_version  bm25 over 3673 chunks
correction_store_version none
model_roles              none
commit                   recorded per run
manifest hash            25aab28a0fe14fbb
```

`model_roles` is `none` because no semantic role in this project is bound to a model: extraction,
investigation, judging and embedding all run deterministically. That is recorded rather than omitted,
because an absent field and a field that is deliberately empty are different claims.

## The leakage audit found a defect in itself, which is the point of writing one

The first run failed, naming `15/9-F-5` as a hold-out well that had been fitted on. The failure was
the check's.

Section 16's hold-out is **by well and governs the drilling-report layer**. Production is split
**temporally** by section 10. Nothing leaks by fitting production on a well whose drilling reports are
held out, because the two layers share no data, and section 16 says of this very well that it "has no
production development days and is already excluded from production hold-out scoring as a cold start".
Check 1 as pre-registered had extended to "any model fit", which applied the wrong hold-out to the
wrong layer.

A second defect sat in the harness: it passed every well with any development row as a well that had
been fitted on. `15/9-F-5` has 2,429 development rows and **zero** valid producing days, so no model
was ever fitted to it. Protocol amendment 5 records both.

Worth saying plainly, because it is the argument for building the audit at all: a check that could not
fail would have reported this project clean on its first run, and this one reported itself wrong
instead.

## Calibration: bands, and why there are no outcome rates

Fourteen development episodes. A calibrated probability from fourteen outcomes has a per-bin interval
roughly 25 points wide, so section 19.4 fixed bands before any score was computed, from six features
that are all observable and none of which is a model's stated confidence.

| band | n | verdicts in it |
|---|---:|---|
| `high` | 8 | 5 `supported_explanation`, 3 `multiple_plausible_explanations` |
| `moderate` | 6 | 4 `insufficient_evidence`, 2 `supported_explanation` |
| `low` | 0 | — |

**Every abstention is in `moderate` and none is in `high`**, which is the relationship one would want.
It is also **partly circular**, and that matters more than the result: two of the six features,
channel availability and whether the run was curtailed, are inputs to the stop conditions that produce
an abstention in the first place. So the band tracks the controller's own reasons for abstaining, not
an independent assessment of them. A band-versus-verdict table is therefore a consistency check and
not evidence that the score is informative.

No reliability diagram, no Brier score, no expected calibration error, and no outcome rates. Bands are
calibrated against whether the conclusion was right, and section 18.8 records that nobody available to
this project can say whether it was. Section 19.4 fixes what a later version must settle first: the
outcome definition, who determines it, the calibrator and the interval.

## Trajectory, stability and cost

14 investigations, 9 to 15 steps each, mean 10.9. Retrieval passes per run: 7 runs made one pass, 5
made two, 2 made three. Zero repeated identical queries. Zero tokens and zero cost.

Verdict stability is exactly 1.0 across repeated runs, and that figure is worth nothing on its own: no
model is called, so repeating a run is arithmetic. Section 19.7 requires it to be reported as
determinism rather than as reliability, and the harness prints that sentence beside the number.

## The false-root-cause rate, and the half that is missing

One finding claims a documented root cause. Its cited spans state a reason, so the mechanical half
passes with one claim examined rather than with none, which is the difference between a gate that held
and a gate that was not reached.

The half needing a domain reader is deferred: a finding whose root cause is cited correctly and is
nonetheless the wrong explanation cannot be detected here. Section 19.5 fixes the asymmetry the plan
asks for **before** any adjudication exists, so it cannot be chosen afterwards: a false confident
root-cause claim counts five, an unnecessary abstention one.

## CI, and what can spend money

The free workflow runs on every push and pull request, passes with no API key, and now runs this
harness so that a leakage finding fails the build. It references no secret at all, which is checked by
a test rather than by reading it.

The paid workflow has **no `push`, no `pull_request` and no `schedule` trigger**. Their absence is the
control, not a condition inside a job: a workflow that can only be started by hand cannot be started by
a merge or by a cron line somebody adds later. It also asks a person to type a confirmation before any
credential comes into scope. It currently does nothing, because no provider key is configured, and it
says so rather than appearing to have run a benchmark.

## What this phase does not do, and why each one is a decision

| not measured | why | what would settle it |
|---|---|---|
| Hold-out anything | section 10 reserves it for one scored run in Phase 8, and 19.2 gates against reaching it | Phase 8 |
| Episode precision and recall | 14 episodes from one detector on two wells is not a benchmark | a curated episode set; section 19.11 declines to manufacture one |
| Retrieval recall at k | needs a gold evidence set, which needs the curated episodes | both, in that order |
| End-to-end correctness | needs a reader with drilling-operations experience | the section 17.4 adjudication |
| Hypothesis-set precision and recall | the same | the same |
| Risk–coverage curve | needs correctness; three bands give three points | correctness, and more episodes |
| Calibrated confidence | 14 episodes | more episodes and an outcome definition |
| Prose-judge scores | no model provider key | a key; the rubric is already fixed in section 19.8 |
| Interval coverage | the current construction fails by 2 to 4 times | an interval construction that calibrates |

Nine deferred rows is a lot, and listing them is the point rather than an apology. Each is a metric the
plan asked for, and in every case the obstacle is one of three things: this dataset does not contain
what the metric needs, the sample is too small for the number to mean anything, or the project has no
domain reader. The third appears four times, which is why section 18.8 says it twice and section 19
says it again.
