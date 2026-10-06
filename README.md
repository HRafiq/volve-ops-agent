# volve-ops-agent

Evidence-bound AI agents for oil and gas operational investigation using Equinor's Volve
dataset, deterministic analytics, provenance-tracked reasoning, calibrated abstention, and
human review.

## Status

Data profiled, both feasibility criteria executed, the deterministic expectation and episode layer
built and measured, drilling-report extraction running, the development cause-label set produced and
scored against both fixed baselines, and a bounded investigation controller running over all fourteen
detected episodes with its five pre-registered gates passing. No model has yet been called by either
the cause-attribution layer or the investigation layer; both run deterministically, which is what
makes them testable.

The cause labels are **machine-assisted**: produced by a language model applying a labelling guide
written and pushed beforehand, not by a domain expert. That is a real limitation rather than a
caveat, and it cost the project a pass mark. Details below.

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
  before any label was made, plus a section marked as written after it: the seven conventions the
  first pass had to derive, one of which was withdrawn on review.
- [`docs/labelling_results.md`](docs/labelling_results.md) is the label set measured: the
  distribution, both baselines per class, and the two directions in which the only available
  external check on the labels fails.
- [`labels/development_pass1.jsonl`](labels/development_pass1.jsonl) is the label set itself, all
  135 rows, each carrying its provenance, its verbatim span and the rule that settled it.
- [`docs/investigation_results.md`](docs/investigation_results.md) is the investigation layer
  measured: five gates on fourteen episodes, how much each gate is worth on this corpus, and the
  document coverage that bounds what any of it can claim.
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
does not have. `src/volve_ops/investigation/` holds the bounded controller over those services.
Four committed scripts regenerate the published figures: `scripts/run_expectation_study.py`,
`scripts/run_extraction.py`, `scripts/run_label_scoring.py` and `scripts/run_investigations.py`, each
writing a run manifest. A fifth, `scripts/draw_adjudication.py`, draws the expert adjudication
subsample described below.

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

### Cause labels, and the pass mark they cost

The labelled sample is 135 drilling-report events. The labels are produced by `claude-opus-5`
applying the labelling guide, because this project's author has no drilling-operations experience
and cannot say whether "ATTEMPTED TO ENGAGE SEAL ASSY, NO GO" names an equipment failure, a hole
condition, or neither. Labelling anyway would have put a human's provenance on a non-expert's
judgement, which invites exactly the confidence the labels cannot support.

So the provenance is recorded on every row and the pass marks that need expert labels are
withdrawn. Protocol section 17 sets this out and amendment 2 suspends them: an extraction model
scored against model labels is compared with a labeller of its own kind, and agreement cannot be
separated from shared convention. A labelled event cannot be constructed in code without declaring
its provenance, and `approach_is_selected` returns false whenever any condition is suspended rather
than taking the conjunction over the survivors, because both survivors are conditions an approach
controls unilaterally. While the suspension holds, the cause layer has no gate that can fail for
being wrong about a cause, which is the cost in its sharpest form.

Section 17.4 fixes what would restore the marks, before any of it is available: a domain reviewer
adjudicates 40 events, and raw agreement of 80 percent with a Clopper-Pearson lower bound above 70
restores them. The draw is done rather than promised, at a pre-registered seed, with a worksheet
carrying exactly the evidence the protocol permits a labeller. It also fixes which version of the
guide an adjudicator is given, because the current one describes how several of the drawn events
were resolved.

What still holds, because none of it depends on a cause being right. Both section 14.3 pass marks
pass on an independent walk of the source XML: 617 qualifying blocks in the sample's 99 documents,
617 events, every duration matching its own timestamps. All 60 attributed labels carry a verbatim
span, machine-checked on every read. The scope is narrow on purpose: both marks can pass while other
extracted fields are wrong, including the two the cause layer is built from.

What the measurement found. `not_stated` is 55.6 percent of the sample, so a system that cannot be
scored on abstention would be rewarded for guessing on more than half of it. `echo-statedetail` is
the better baseline on both metrics, at macro-F1 0.3329 against 0.2992, because the free
`stateDetailActivity` flag reaches F1 0.633 on equipment failure with no reading at all. And roughly
half the sample carries a source subcategory that points at a cause the comment does not support,
which is why the subcategory baseline manages 0.057 on equipment failure despite having a table
aimed at it.

Two findings worth more than the scores. **Two of the twelve taxonomy classes turned out to be
unreachable**: the guide's top-ranked precedence rule sends any comment that would earn
`equipment_maintenance` or `rig_service` to `not_stated` instead. The first labelling pass carved an
exception, independent review rejected it, and the correction changed both baselines' scores and
which one leads. And where both baselines name an actual cause and agree, **the labels match on one
event in sixteen**. Either the structured fields are badly wrong about those events or the labels
are, and the project cannot currently say which.

### The investigation layer

The controller owns nine declared stages and four stop conditions. A model's judgement enters at
exactly two points: how to phrase a retrieval query, and whether another evidence pass is justified.
It is never asked what to do next from an open list of tools.

All five pre-registered gates pass over the fourteen episodes. The one that earns its place
unassisted is replay: the trace records the judgements rather than the output, so replaying
recomputes the finding instead of reading it back, which makes it a determinism test on the
controller. The others are reported with how much that is worth on this corpus, because independent
review pointed out that two of the five have almost nothing to examine here. The provenance gate
itself is not weak: review built a finding citing another well's report from five years away under a
fabricated filename, with invented figures and a root-cause claim, and the first version of the gate
passed it. All four holes are closed and the reconstruction is a test.

**One episode in fourteen gets a documented root cause.** `15/9-F-14` from 31 January 2012, citing a
report dated the day before: *"Closed in well to prepare for handover."* The choke reduction the data
established is explained, cited verbatim. The other thirteen have nothing to cite: not one of the
3,673 extracted drilling-report events falls inside any episode window, and at ±45 days twelve of
fourteen have none. The reports cluster in 2007–08 and 2016 while the episodes fall in 2009–14,
because a daily drilling report is written when a rig is on the well and a producing well has no rig.

An earlier version of this README claimed zero citations and a structurally unreachable top level.
Both were wrong: the level was never implemented, and retrieval was asking about the wrong hypothesis
on the one episode where documents existed. Review caught both, and
[ADR 0008](docs/architecture_decisions/0008-drilling-reports-rarely-overlap-production-episodes.md)
records the correction alongside the finding, because an ADR that reasons from a correct table to a
self-flattering conclusion is the more useful thing to have written down.

Three episodes stop earlier still, on `mandatory_evidence_unavailable`: `15/9-F-12` has usable
downhole pressure on 31.2 percent of its producer rows where counting non-empty cells reports 99.8,
because 2,095 rows record `0.00` on a gauge three kilometres down. The controller does not impute it
and the gate will not let a hypothesis that needs it be called supported.

Against the fixed `strongest-deviation` baseline, which reads nothing, the controller agrees on 5 of
the 7 episodes where both named a driver. That figure is reported with its weaknesses: the two share
most of their implementation, so it largely measures shared code, and an earlier version reported 5 of
6 by dropping the one episode where they disagreed.

This is the third pre-registered capability the dataset has constrained, after both feasibility
criteria, and all three are constrained the same way: Volve is generous about measurements and thin
about the operational record that explains them.

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
