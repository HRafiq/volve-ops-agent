# Investigation results: the bounded controller on the development episodes

Regenerate with
`python scripts/run_investigations.py "data/cache/Volve production data.xlsx" data/cache/ddr_xml`,
which writes a trace and a finding per episode plus a run manifest. Every figure here is printed by
that script.

Protocol section 18 fixed the gates before any investigation ran and was pushed as `prereg-v4` before
this layer existed. Its thresholds were not fixed then: every numeric threshold the layer needed was
chosen afterwards and is recorded in protocol amendment 4 as post-inspection. Two of them move figures
on this page, and the amendment says which.

**No model is called.** The judgement role is the deterministic one in the controller. That is not a
placeholder: an investigation whose correctness depended on a model would be one nobody could test,
and section 18.6 needs an opponent that existed before any model ran.

## The five gating pass marks, and how much that is worth

| section 18.7 pass mark | result | can it fail on this corpus? |
|---|---|---|
| Provenance validity is 100 percent | pass, 14 of 14 | weakly |
| Stop-condition honesty is 100 percent | pass, 14 of 14 | yes |
| Trace replay is exact | pass, 14 of 14 | yes |
| Abstention is reachable and used | pass, 4 of 14 abstain | yes |
| No forbidden root-cause wording | pass | weakly |

**The third column is there because independent review pointed out that "all five pass" carried less
information than it appeared to**, and that is worth stating in the document rather than leaving a
reader to work out.

Provenance validity is weakly falsifiable *here* because only two document citations exist in the
whole run, so the two citation rules have almost nothing to examine, and because the narrative
generator states no figures at all, so the unsourced-number rule is never exercised by it. The gate
itself is not weak: review built a finding that cited a different well's report from five years away
under a fabricated filename, with seven invented figures and a root-cause claim, and the first version
of the gate passed it clean. All four holes are closed and the reconstruction is now a test. But a gate
that holds and a gate that was tested by this run are different claims, and only the first is made.

The wording check is weakly falsifiable for the same kind of reason: the narrative is generated from
the causal level, so it will not drift unless the generator does. It is a backstop against a future
model-backed role, and it is a four-phrase blacklist, which review showed can be evaded by
"the underlying reason was" and "originated from". Those two are now caught; the next two are not.

Replay is the one that earns its place unassisted. The trace records the judgements rather than the
output, so replaying recomputes the finding instead of reading it back. Any hidden nondeterminism, an
unordered set reaching output or a timestamp folded into a field, would make the recomputed finding
differ. It is a determinism test on the controller wearing a provenance test's clothes.

## What the layer concluded

14 episodes over 6 development wells, from the section 9 detector. The agent does not choose its own
episodes: a model picking interesting periods would be selecting the cases it can explain.

| verdict | n | | stop condition | n | | highest causal level | n |
|---|---:|---|---|---:|---|---|---:|
| `supported_explanation` | 7 | | `evidence_exhausted` | 7 | | `supported_mechanism` | 5 |
| `insufficient_evidence` | 4 | | `evidence_threshold_met` | 4 | | none | 5 |
| `multiple_plausible_explanations` | 3 | | `mandatory_evidence_unavailable` | 3 | | `proximate_driver` | 3 |
| | | | | | | `documented_root_cause` | **1** |

## The one documented root cause, and why there is only one

Two document citations across all fourteen findings. One episode reaches the top causal level:
`15/9-F-14` from 31 January 2012, citing a report dated 30 January, one day before onset:

> "Closed in well to prepare for handover."
> "Waited for Production Department to prepare well for handover."

The choke reduction the structured data established is explained: the well was closed in and handed to
the Production Department. Cited verbatim, and the gate passes it.

The other thirteen have nothing to cite. Not one of the 3,673 extracted drilling-report events falls
inside any episode window; at ±45 days, 12 of 14 have none, and both episodes with any overlap are on
the same well. The reports cluster in 2007 to 2008 and 2016 while the episodes fall in 2009 to 2014,
because a daily drilling report is written when a rig is on the well and a producing well has no rig.

[ADR 0008](architecture_decisions/0008-drilling-reports-rarely-overlap-production-episodes.md) records
this, and records that an earlier version of this document asserted zero citations and a structurally
unreachable top level. Both were wrong: the level was unimplemented, and retrieval was asking about the
wrong hypothesis on the one episode where documents existed. Independent review caught both. The
corrected figure is one in fourteen rather than zero, and the limitation is real but narrower than the
project first claimed.

The window matters to this claim and is named with it: at ±180 days, 10 of 14 episodes still have no
report in range, but 4 do rather than 2. `EVIDENCE_WINDOW_DAYS = 45` was chosen after the protocol was
tagged and is recorded as a post-inspection parameter.

## Where the data runs out, and what the controller does about it

Three episodes stop on `mandatory_evidence_unavailable`, all on `15/9-F-12` after February 2011, all
for the same reason: no usable downhole pressure. `docs/data_profile.md` records that F-12 has pressure
on 31.2 percent of its producer rows, where counting non-empty cells reports 99.8 percent, because
2,095 of its rows record `0.00` on a gauge three kilometres down.

The controller does not impute it, and the gate will not let a hypothesis that declares a dependency on
it be marked supported. Those three return `insufficient_evidence` with the missing channel named in
the finding. A fourth episode, `15/9-F-12` from August 2011, also lacks pressure and still concludes,
on water cut, which needs no pressure: the rule is per hypothesis, not per episode.

## Against the fixed baseline, and why the comparison is weaker than it looks

`strongest-deviation` is fixed in section 18.6 and exempt from amendment. It reads nothing, ranks the
mandatory channels by movement against the well's own pre-episode window, and never claims a documented
root cause. It abstains on 7 of 14 episodes.

Where both named a driver, they **agree on 5 of 7** at the level of the physical event.

Three things about that number, in descending order of how much they should reduce your confidence in
it.

**The two systems share their implementation.** The baseline ranks the same five channels by the same
standardised shift computed by the same function at the same 1.0 threshold. The controller is that
baseline plus a materiality filter and two hypotheses the baseline has no vocabulary for. So 5 of 7
largely measures shared code, not independent agreement, and it is a weaker opponent than section 18.6
intended. It is not a straw opponent, which was the risk the protocol guarded against; it is closer to
a near-duplicate, which is a different problem and arguably worse for the comparison.

**The comparison is at the level of the event, not the column.** The baseline names "increased choke
differential pressure" where the controller supports choke reduction, and those are the same event:
closing a choke raises the differential across it. Scoring them apart gave 2 of 7.

**The denominator was wrong in an earlier version of this document.** It reported 5 of 6, having
returned "no comparison" for the one episode where the controller's supported hypothesis lay outside
the baseline's vocabulary: `15/9-F-12` in January 2010, where the baseline names falling wellhead
pressure and the controller supports water breakthrough. Both named a driver and they named different
ones, so it is a disagreement. 5 of 6 was the most favourable of three available framings.

## What a model-backed role would add

The deterministic role reaches `documented_root_cause` through a lexical test: a cited span containing
one of ten intent phrases, landing on a hypothesis the data already supports. That is a proxy for a
judgement and it is worse than a model would be, both in what it will miss and in what it will accept.
It exists because without it no code path could emit the level at all, which is how the first version
of this layer came to publish a claim about why the level was never reached.

Where a model would contribute: reading a comment that states a reason without using one of those
phrases, distinguishing a reason from a coincidence, and judging whether narrative evidence supports a
mechanism rather than merely mentioning it. None of that can be demonstrated against
`strongest-deviation` on this layer, because there are two citable documents in the whole corpus for
these episodes. ADR 0008 says so, and section 18.8's deferred pass marks should be settled on the
drilling-report layer, where the documents are.

## What is not here

No correctness figure. Protocol section 18.8 defers it with no threshold invented, because scoring
whether a choke reduction explains a shortfall on a specific North Sea well needs a reader this project
does not have. Section 17 records the same limitation for the cause labels; this is the second time it
has bitten and the protocol states it twice rather than mentioning it once.

Concretely: none of the five gates can fail because an explanation is wrong. They can fail because a
citation is fabricated, a figure is unsourced, a stop condition is misreported, a trace does not
replay, or a finding overclaims or underclaims its level. Correctness is not among them.

No hold-out investigations. Section 18.9 keeps the hold-out out of this phase, and section 10 scores it
once, in Phase 8.

No value shortfall unless an oil price is passed on the command line. The script computes one only
from a stated assumption, and the finding records the assumption beside the number rather than
presenting a currency figure as a measurement.
