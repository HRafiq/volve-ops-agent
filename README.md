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
| 5 | Agent B: NPT post-mortem, lessons register, correction store | **complete** |
| 6 | Operator console | **complete** |
| 7 | Failure, health and security experiments | **complete** |
| 8 | Frozen hold-out scored once, public write-up | **next** |

The hold-out has never been scored and never been looked at. Phase 4's leakage audit exists to prove
that mechanically rather than assert it, and it gates the build.

159 tracked files, 703 tests, ruff and mypy strict clean. No model is called by any layer yet: every
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
baseline, which cannot detect sustained underperformance by construction.

Calibration fails, and the figure that matters is the one the detector uses. Section 8 gates the
**lower-tail exceedance rate** at 0.05 to 0.20: the two candidate models pool at 0.302 and 0.387, and
`naive-median28`, the fallback actually in use, at **0.5632** over a 7-day horizon. Section 8's
calibration condition has never been evaluated for it, because the conditions are applied to
candidates and this model is the fallback. [Details](docs/expectation_results.md)

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
| Source subcategory contradicting its own comment | 21 of 135, 15.6 percent |

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

**Operator console.** A read-only review tool over the same payloads, served by the API that
produces them. All eight of section 21.6's gates pass and none examines nothing: 631 payload figures
resolve to a manifest key, a fact id, an event id, an artifact file or a pre-registered rule; 15 routes enumerated,
and the only four that accept anything but GET are the review actions.

| Figure | Value |
|---|---|
| Payload figures resolving to a source | 631 of 631 |
| Routes that write | 4 of 15, all of them review actions |
| Abstentions rendering as their own state | 4 of 4 |
| Currency figures published | 0, because no oil price was supplied |

Its first rule is the one that makes the rest checkable: **the console renders and does not
compute.** Where it needed a figure no manifest held, the harness that owns the figure was extended
rather than the console allowed to derive it. That forced out a result nobody could previously read:
the selected expectation model's lower-tail rate is **0.563** at a 7-day horizon against a protocol
band of 0.05 to 0.20, so 56 percent of evaluated days fall below a bound that permits at most 20. The
expectation panel shows it where the band is drawn. [Details](docs/console_results.md)

**Post-mortem and lessons register.** Non-productive time is 8,563 hours of 39,495 recorded, 21.7
percent. The register is built from the source's own fields rather than from the machine-assisted
labels, and 13 recurring patterns account for 6,230 of 7,430 development hours, 83.9 percent. All
seven of section 20.6's gates pass. **Five of the seven could not fail when first written**, and one of
those five was wrong three times running, so there are six defects across four rounds of independent
review, each round checking the previous round's fixes. All seven are now functions with a test that makes
each fail.

| Figure | Value |
|---|---|
| Largest recurring pattern | waiting on weather, 1,595 hours over 7 wells and 372 events |
| NPT share, worst well to best | 36.3 percent on `15/9-19` against 7.8 percent on `15/9-F-10` |
| Corpus non-productive hours held out and not reported | 13.2 percent, because 4 of 11 wells are hold-out |
| Events in recurring patterns carrying a cause label | **65 of 2,600, 2.5 percent** |

That last row is the finding that bears on the rest of the project. The labelled sample is stratified
by subcategory so rare ones appear at all, which buys per-class scorability and pays for it in hours
covered: the 1,595-hour weather pattern has 9 labels in 372 events. The sample is right for scoring a
classifier per class and close to wrong for explaining where the time went, and this project had only
been making the first claim.

The register's own limitation is published beside it. Its bar is three wells, so the 38 patterns it
excludes include sidetracks, lost circulation, well control and casing, which are the first names an
operations reader would look for. The largest single exclusion is 562 hours of sidetrack time on one
well, 7.6 percent of development non-productive hours, kept out by the three-well bar and not by its
size. [Details](docs/postmortem_results.md)

**Health, security and failure experiments.** 38 injection payloads in six classes carried through
the real path a drilling report takes, 21 attack fixtures against the parser and archive hardening,
seven provenance-failure classes put to the publication gate, and four capability ablations.

The first thing this phase had to settle is what "injection" can mean here at all. The design brief
lists seven prompt-injection invariants and every one presumes document text reaching a language
model. **No module in this project calls one.** Three are therefore vacuous, and the suite declares
them vacuous with the reason rather than collecting three free passes: a vacuous invariant can never
produce a held result, because the outcome enum has a separate member for it.

Removing the model moves the attack surface rather than removing it. What is left is data injection
against deterministic consumers, and the live question is which consumers *interpret* their input
instead of recording it. Almost all of them record. The console interprets, because a browser
interprets markup, which makes the rendering layer the live channel and the one the brief does not
mention.

| Figure | Value |
|---|---|
| Invariants held / violated / fixtures that never arrived | 228 / **0** / **0** |
| Invariants declared vacuous, not counted as preserved | 3 of 7 |
| Hostile characters rendered in the evidence drawer, as inert text | 884 |
| Unescaped-markup sinks in the console | 0, after removing the one that existed |
| Attack fixtures refused by the ingest hardening | 21 of 21 |
| Published figures contradicting the record they cite | 0 |

The pre-registration named this phase's likely defect in advance, and it fired. A hostile string in a
field no parser reads passes every invariant while testing nothing, so every fixture must prove its
payload arrived. The first honest run found the payload in **none** of the published artifacts for
every markup fixture: the controller quotes the first sentence carrying a term from its closed query
map, so a payload appended as a trailing sentence is never published at all. **Only text the
controller selects as a quote is ever published.** The first version of the check called that a
violation and would have reported sixteen security failures that were nothing of the kind.

Writing tests for every route rather than the obvious ones found the API's one route that validated
nothing: `GET /api/investigations/{id}/review` consulted the review log and never the store, so any
string came back `200` with a review state and the string echoed as an investigation id. Not a
traversal, since no path was built from it, but an episode that does not exist got a confident review
panel.

The ablations produced one result worth arguing with. The most accurate expectation model of the five
is also the one that opens the most investigations.

| model | episodes opened | WAPE |
|---|---:|---:|
| naive-median28 *(selected)* | 14 | 0.1211 |
| hyperbolic-decline | 11 | 0.1199 |
| choke-scaled | **18** | **0.0984** |

Accuracy and investigation volume move in opposite directions here, which is the measurement a WAPE
table cannot make. Removing the in-window document from the one episode that has one drops the
finding from `documented_root_cause` to `proximate_driver` while the verdict and evidence band hold,
which is exactly what the retrieval stage exists to lift. [Details](docs/security_results.md), and
[SECURITY.md](SECURITY.md) for the trust boundaries and the known limitations.

## The three things I learned

**A check written in the same breath as the thing it checks tends to test that thing against itself.**
This happened in five consecutive phases, and in Phase 5 it happened again inside the fix for it. The
worst case was a leakage audit whose central check tested whether a fitted day fell outside the
development window, over a day set it had built with the same filter. An independent review made the
expectation study fit on the whole record and the audit reported clean. The fix was structural: the
scripts record the dates they actually fitted on, and the audit reads those. Reproducing the same leak
now yields 5,108 out-of-window dates across six wells and a failed build. A check cannot audit another
script's filtering by re-deriving it.

The Phase 5 version is the one I would show a reviewer. Three gates could not fail, I fixed them and
wrote the amendment recording the fix, and a second review found that two of the replacements also could
not fail and that one correction the amendment claimed had not been made anywhere. The generalisation
that came out of it: **ask the artifact, never the function that produced it.** All five instances
interrogated the producer. And an amendment is a claim about a repository, as checkable as any figure in
it, so writing one in the same session as its own fixes is the same mistake one level up.

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

Fourteen metrics the plan asked for are deferred, each with its obstacle named in
[`docs/results_table.md`](docs/results_table.md) beside the 172 rows that carry a figure. Every
obstacle is one of three things: the dataset lacks what the metric needs, the sample is too small for
the number to mean anything, or there is no domain reader. The third is named in four of the thirteen
and a fifth depends on one of those.

14 episodes from one detector on two wells is not a benchmark, and the protocol declines to
manufacture precision from it.

## How it is put together

`src/volve_ops/domain/` holds the deterministic engine. `src/volve_ops/tools/` wraps it in typed,
bounded tools that refuse an over-large request rather than truncating it, and
`src/volve_ops/mcp_server/` exposes those over MCP as an optional extra. The adapter decides nothing,
which is the point: a rule about what a caller may ask for lives in the tool layer, once.

`extraction/` turns drilling reports into typed events in a versioned store, `retrieval/` indexes
their narrative lexically, `provenance/` holds a fact ledger that refuses a derived value whose inputs
it does not have, `investigation/` is the bounded controller, `postmortem/` aggregates recorded time and
holds the append-only correction store, and `evaluation/` is the harness that judges the project's own
account of itself.

## Reproduce

Each script writes a run manifest, and a figure without one is not reported as a result.

```bash
python scripts/run_expectation_study.py "data/cache/Volve production data.xlsx" data/cache/ddr_xml
python scripts/run_extraction.py data/cache/ddr_xml
python scripts/run_label_scoring.py labels/development_pass1.jsonl
python scripts/run_investigations.py "data/cache/Volve production data.xlsx" data/cache/ddr_xml
python scripts/run_postmortem.py data/cache/ddr_xml
python scripts/run_evaluation.py "data/cache/Volve production data.xlsx" data/cache/ddr_xml
python scripts/run_console_checks.py
```

The console needs its optional extra, and serves itself from the API process:

```bash
pip install -e ".[console]" && npm --prefix frontend install && npm --prefix frontend run build
python -m uvicorn api.main:app --port 8000
```

The last one is the gate: it exits non-zero on a leakage finding or an unreported figure. Raw and
processed data are never committed; [`docs/data_manifest.md`](docs/data_manifest.md) records every
file read with checksums, and the one exception is recorded there too.

CI is split so money cannot be spent by accident. No workflow an event can start may read a secret,
checked by parsing every workflow file. Anything that would call a model is manual only.

## Documents

| Document | What it is |
|---|---|
| [`docs/eval_protocol.md`](docs/eval_protocol.md) | The pre-registration. Its commit history is the evidence, tagged `prereg-v0` through `prereg-v15`, with no `v10` and section 13 saying why |
| [`docs/data_profile.md`](docs/data_profile.md) | What the data turned out to be, and the coverage gaps that limit what can be claimed |
| [`docs/results_table.md`](docs/results_table.md) | Every figure in the project, with its denominator and whether it is gated, reported or deferred |
| [`docs/architecture_decisions/`](docs/architecture_decisions/) | Nine decisions, including all three feasibility outcomes |
| [`labels/development_pass1.jsonl`](labels/development_pass1.jsonl) | The label set itself, each row with its provenance, span and the rule that settled it |
| [`docs/postmortem_results.md`](docs/postmortem_results.md) | Where the non-productive time went, and how little of it any label characterises |
| [`docs/console_results.md`](docs/console_results.md) | What the operator console shows, what it refuses to show, and the six defects building it found |

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
