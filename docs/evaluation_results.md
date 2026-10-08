# Evaluation results: the harness, the leakage audit, and what this project cannot measure

Regenerate with
`python scripts/run_evaluation.py "data/cache/Volve production data.xlsx" data/cache/ddr_xml --table docs/results_table.md`.
Its exit status is the gate. It calls no model.

Protocol section 19 fixed the gates before the harness existed and was pushed as `prereg-v6`.
Amendment 6 then corrected three of those gates after independent review showed they could not fail,
and every figure below is the corrected one.

The consolidated table is [`results_table.md`](results_table.md): 150 rows, each carrying its
denominator, its status, what would settle it if deferred, and the caveat that belongs with it.

## Three of the six pass marks could not fail, and review found all three

Section 19 now has seven marks. The seventh is amendment 8's: every table row must name a figure that
exists, which is the converse of the coverage gate below. What it was added for: 12 of the 145 rows in
the table as last committed read "not produced", the five section 20.6 gate rows among them, while the
manifest recorded every gate as true. The other seven were three label classes with no labels, two
applied rules nothing applied and two stop conditions nothing reached, each a counter that omits what it
never saw. The coverage half could see none of it, because it compared path strings without asking
whether they resolved.

This was the third phase in which that had happened here, and by the end of Phase 5 it was the fifth.
The pattern is specific enough to name:
**a check written in the same breath as the thing it checks tends to test that thing against itself.**

| gate | the defect | what it does now |
|---|---|---|
| 19.2 leakage, check 3 | tested whether a fitted day fell outside the development window, over a day set the harness had built with `development_only`: the negation of the comprehension that produced its own input | the scripts record the dates they actually fitted on; the audit reads those |
| 19.1 field presence | ran `missing_fields` on a freshly validated model whose validator already refuses a blank field | runs against the manifest read back from disk |
| 19.1 hash reproduces | compared a hash with the hash of `model_copy()` of the same object | compares against the hash the previous run persisted, on the same commit |

The leakage one was not theoretical. Review made the expectation study fit on the whole record, 3,201
hold-out producing days included, and the audit reported **clean** with all six marks passing. The same
leak now produces:

```
leakage audit: FINDINGS
  ! 15/9-F-12: 876 recorded fitted dates are outside the development window, first 2014-04-26
  ...
  FAIL  19.2 leakage audit clean
```

5,108 out-of-window dates across six wells, and a non-zero exit. A run that records no fitted dates at
all is also a finding now rather than a pass, because a check with nothing to audit is not a clean check.

## The seven gates, as they stand

| section 19 pass mark | result | what it examined |
|---|---|---|
| 19.1 every field present in the persisted manifest | **pass** | 9 fields of the previous run's manifest |
| 19.1 manifest hash reproduces on the same commit | **pass** | this run against the last run at the same commit |
| 19.2 leakage audit clean | **pass** | 9,540 recorded fitted dates, 135 labels, 7 labelled wells, 5 wells in the investigation population |
| 19.3 every manifest figure has a table row | **pass** | 0 uncovered across five run manifests |
| 19.3 every table row names a figure that exists | **pass** | 0 unresolved of 150 rows |
| 19.5 no mechanical false root-cause claim | **pass** | 1 documented claim |
| 19.7 no repeated identical tool call | **pass** | 14 traces, 23 retrieval queries |

One check examines nothing: `correction_from_the_hold_out`. The store exists and is empty, because a
correction is a person changing a value and no person has changed one. The harness prints it under
"checks that examined nothing" rather than letting it count as clean, and protocol amendment 8 withdraws
section 20.5's promise that Phase 5 would end the vacuity.

**§19.5 is a consistency check, not a safety measurement**, and that is now said in the protocol and in
the code. The causal level is assigned by exactly the condition this gate tests, through the same
function and the same phrase list over the same spans, so **no finding this controller produces can fail
it**. It is kept because a controller that stopped enforcing its own rule would be caught, and because a
finding from any other producer would be checked properly. An independent version needs the reason
re-derived by something that did not assign the level, which is a judgement and is deferred.

## The leakage audit found three things wrong with itself and its own protocol section

Beyond check 3, review found:

**`15/9-F-5`, a section 16 hold-out well, was inside the population every investigation read.** The
offset comparison in the diagnostic bundle iterates that population, so its rows were an input to all
fourteen findings, while it produced no finding of its own and so was invisible to a check that looked
at findings. Check 5 now covers the whole population. The well is also out of both producing-well
populations at the source: it is a water injector with 2,429 development rows and **zero** valid
producing days, and `15/9-F-4` has exactly the same shape. Removing them changed no figure, which
confirms they contributed nothing, and it corrects a "six producing wells" denominator this project had
been publishing. The development number is **five**.

**Amendment 5's claim that "the two layers share no data" was false.** The production layer consumes
drilling-report activity dates through `stable_reference_windows`. The precise statement, now in the
protocol, is that section 16 governs which wells may be labelled or investigated, and nothing scored on
the production layer is scored on a hold-out well's drilling reports.

**Section 13 was silent on relaxing a failed check**, having forbidden only tightening one. Relaxing is
the cheaper version of the same move, and amendment 6 closes it: an amendment that weakens a check which
has just failed must state what the check was examining, why the failure was the check's rather than the
project's, and what still audits the thing the check was for.

## Calibration: bands, and a corrected distribution

Fourteen episodes. A calibrated probability from fourteen outcomes has a per-bin interval roughly 25
points wide, so section 19.4 fixed bands before any score was computed, from observable features and
never from a model's stated confidence.

**A sixth feature was inert and has been removed.** `absence_of_contradiction` read the
`Hypothesis.contradicting` field, which nothing in the codebase ever writes, so it sat at 1.0 on all
fourteen findings and lifted every score by a constant. The previously published distribution had no
`low` band at all, which was an artifact of it.

| band | n | verdicts in it |
|---|---:|---|
| `high` | 7 | 4 `supported_explanation`, 3 `multiple_plausible_explanations` |
| `moderate` | 5 | 3 `supported_explanation`, 2 `insufficient_evidence` |
| `low` | 2 | 2 `insufficient_evidence` |

**The relationship between band and verdict is arithmetic, not a finding**, and the earlier version of
this document got that wrong in the Phase 3 way: a correct table read flatteringly. Four of the five
features are derived from inputs to the verdict itself. The standardised shift sets every hypothesis
status; channel availability triggers the unavailable-evidence stop; a documentary cause requires a
supported hypothesis; and `ran_to_completion` **is** the stop condition. Only `window_completeness` is
independent, and on this corpus it takes three values between 0.989 and 1.0. So abstention and a low
band share a cause, and the table above is a consistency check.

One thing a reader should not take from the word "high": **6 of the 7 high-band findings cite no document
at all.** Documentary evidence is one feature of five and the rest are structured-channel arithmetic, so
a high band means the channels moved clearly and the run completed, not that anything was read.

No reliability diagram, no Brier score, no outcome rates. Section 19.4 fixes what a later version must
settle first: the outcome definition, who determines it, the calibrator and the interval.

## Trajectory, stability and cost

14 investigations, 9 to 15 steps each, mean 10.9. Retrieval passes per run: 7 made one, 5 made two, 2
made three, for **23** queries in total. Zero repeated identical queries. Stop conditions: 7
`evidence_exhausted`, 4 `evidence_threshold_met`, 3 `mandatory_evidence_unavailable`. Zero tokens and
zero cost.

A `verdicts_stable` field used to sit here, defaulted to true and set by nobody, reported as though it
were a measurement. It is gone. The measurement that exists is section 18.7's replay mark, which
recomputes each finding from its trace and passes on all fourteen; with no model called, that is
determinism rather than reliability, and the harness prints that sentence beside it.

## The version freeze

Nine fields, none blank, absence recorded as `none` rather than omitted. `model_roles` is `none`:
extraction, investigation, judging and embedding all run deterministically.

The manifest hash is **not quoted here**, deliberately. The commit is one of the nine hashed fields, so
the hash changes with every commit, and an earlier version of this document published a hash taken from
an uncommitted tree whose `commit` field pointed at a tree containing no harness, five lines below a
pass mark claiming reproducibility. The live value is in `data/cache/evaluation_run.json`.

## CI, and what can spend money

The free workflow references no secret at all, which a test checks by parsing the workflow rather than
by anyone reading it.

**It does not run this harness on GitHub, and saying otherwise was wrong.** The harness needs the cached
dataset, `/data/` is gitignored, so the condition guarding the step is always false on a runner and the
step reports a skip. What protects the gates on every push is `tests/test_evaluation.py`, which
exercises each one's failing case; the harness over real data runs for anyone with the share locally.

The paid workflow has no `push`, no `pull_request` and no `schedule` trigger. Their absence is the
control rather than a condition inside a job. It also takes the confirmation through an environment
variable rather than interpolating a free-form string into a shell command, which is how the first
version was written and is a textbook Actions injection.

## What this phase does not do, and why each one is a decision

| not measured | why | what would settle it |
|---|---|---|
| Hold-out anything | section 10 reserves it for one scored run in Phase 8, and 19.2 gates against reaching it | Phase 8 |
| Episode precision and recall | 14 episodes from one detector on two wells is not a benchmark | a curated episode set; section 19.11 declines to manufacture one |
| Retrieval recall at k | needs a gold evidence set, which needs the curated episodes | both, in that order |
| End-to-end correctness | needs a reader with drilling-operations experience | the section 17.4 adjudication |
| Hypothesis-set precision and recall | the same | the same |
| Risk and coverage curve | needs correctness; three bands give three points | correctness, and more episodes |
| Calibrated confidence | 14 episodes | more episodes and an outcome definition |
| Prose-judge scores | no model provider key | a key; the rubric is already fixed in section 19.8 |
| Interval coverage | the current construction fails by 2 to 4 times | an interval construction that calibrates |

Nine deferred rows at the end of this phase, and listing them is the point rather than an apology. Every
obstacle is one of three things: the dataset does not contain what the metric needs, the sample is too
small for the number to mean anything, or the project has no domain reader. The third is named in three of
these nine and a fourth depends on one of them, which is why sections 17, 18 and 19 each say it.

Phase 5 added three more, so `results_table.md` now carries thirteen deferred rows: planned versus actual
drilling time, whether a recurring pattern is a correct lesson, and the correction loop's effect on
extraction quality, all three in [`postmortem_results.md`](postmortem_results.md) with what would settle
each. The thirteenth is the inter-pass label agreement that protocol amendment 2 withdrew, which was
already deferred before this phase and is not in the nine above because that table lists this phase's
own.
