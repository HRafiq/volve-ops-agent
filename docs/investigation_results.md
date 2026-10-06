# Investigation results: the bounded controller on the development episodes

Regenerate with
`python scripts/run_investigations.py "data/cache/Volve production data.xlsx" data/cache/ddr_xml`,
which writes a trace and a finding per episode plus a run manifest. Every figure here is printed by
that script.

Protocol section 18 fixed all of this before any investigation ran, and was pushed as `prereg-v4`
before this layer existed.

**No model is called.** The judgement role is the deterministic one in the controller. That is not a
placeholder standing in for the real thing: an investigation whose correctness depended on a model
would be one nobody could test, and section 18.6 needs an opponent that existed before any model ran.
Where a model would add something is named at the end, along with why it cannot be demonstrated here.

## All five gating pass marks pass

| section 18.7 pass mark | result |
|---|---|
| Provenance validity is 100 percent | **pass**. All 14 findings clear the section 18.5 gate. |
| Stop-condition honesty is 100 percent | **pass**. Every recorded stop matches the controller state, and all 3 curtailed findings say so. |
| Trace replay is exact | **pass**. All 14 traces replay to a byte-identical finding. |
| Abstention is reachable and used | **pass**. 4 of 14 return `insufficient_evidence`. |
| No forbidden root-cause wording | **pass**. No finding below `documented_root_cause` claims one. |

Replay deserves a sentence on what it actually tests. The trace records the two points where
judgement entered, not the output, so replay recomputes the finding with those answers substituted
rather than reading it back. Any hidden nondeterminism in the controller, an unordered set reaching
output, a timestamp folded into a field, would make the recomputed finding differ. It is a
determinism test wearing a provenance test's clothes, and that is why it is worth having.

## What the layer concluded

14 episodes over 6 development wells, from the section 9 detector. The agent does not choose its own
episodes: a model picking interesting periods would be selecting the cases it can explain.

| verdict | n |
|---|---:|
| `supported_explanation` | 7 |
| `insufficient_evidence` | 4 |
| `multiple_plausible_explanations` | 3 |

| stop condition | n |
|---|---:|
| `evidence_exhausted` | 7 |
| `evidence_threshold_met` | 4 |
| `mandatory_evidence_unavailable` | 3 |

| highest causal level reached | n |
|---|---:|
| `supported_mechanism` | 5 |
| `proximate_driver` | 4 |
| none | 5 |
| `documented_root_cause` | **0** |

## The result that bounds everything else: there are no documents to read

**Zero document citations across all 14 findings**, and `documented_root_cause` reached zero times.
Retrieval is not weak. The documents do not exist for these periods.

Not one of the 3,673 extracted non-productive events falls inside any episode window. At ±45 days,
12 of 14 episodes have none. The drilling reports cluster in 2007 to 2008 and again in 2016; the
episodes fall in 2009 to 2014. A daily drilling report is written when a rig is on the well, and a
quietly producing well has no rig.

[ADR 0008](architecture_decisions/0008-documented-root-cause-is-unreachable-for-production-episodes.md)
records the decision not to work around this: the retrieval stage still runs and records that nothing
was citable, the level stays defined and is reported as unreached, and no replacement document source
is substituted after the pre-registered one came up empty.

This is the third pre-registered capability the dataset has declined to support, after B1 and C1, and
all three fail the same way. The Volve release is generous about measurements and thin about the
operational record that explains them.

## Where the data runs out, and what the controller does about it

Three episodes stop on `mandatory_evidence_unavailable`, all on `15/9-F-12` after February 2011, all
for the same reason: no usable downhole pressure. `docs/data_profile.md` records that F-12 has
pressure on 31.2 percent of its producing days, where counting non-empty cells reports 99.8 percent,
because 2,095 of its rows record `0.00` on a gauge three kilometres down.

The controller does not impute it, and the gate will not let a hypothesis that declares a dependency
on it be marked supported. So those three episodes return `insufficient_evidence` with the missing
channel named in the finding. A fourth episode, `15/9-F-12` from August 2011, also lacks pressure but
reaches `supported_explanation` on water cut, which needs no pressure: the rule is per hypothesis, not
per episode.

## Against the fixed baseline

`strongest-deviation` is fixed in section 18.6 and exempt from amendment. It reads nothing, ranks the
mandatory channels by movement against the well's own pre-episode window, and never claims a
documented root cause.

It abstains on 7 of 14 episodes. Where both it and the controller named a driver, they **agree on 5
of 6** at the level of the physical event.

That comparison is reported at the level of the event rather than the column, and the reason is worth
stating because the first version of this document would have been wrong. The baseline often names
"increased choke differential pressure" where the controller supports a choke-reduction hypothesis.
Those are the same event: closing a choke is what raises the differential across it. Scoring them as
disagreement gave 2 of 7 rather than 5 of 6, which would have been a published figure measuring
nothing but which column each side happened to read.

**What 5 of 6 means, said plainly.** On production episodes the reading layer currently adds nothing
over a deterministic ranking of five channels. It reaches a causal level more often, because it can
test water cut and a field-wide constraint and the baseline cannot, and the two disagree about the
driver only once. That is the honest state of the comparison, and section 18.8 is why no pass mark is
claimed from it either way.

## What a model-backed role would add, and why it is not shown here

The deterministic role tops out at `supported_mechanism` by construction. Promoting to
`documented_root_cause` needs a document read and a span cited, and promoting a hypothesis to
supported on narrative evidence needs a judgement a keyword match cannot make. Those are exactly the
things a model would contribute.

It cannot be demonstrated on this layer, because there is nothing to read. Any comparison between a
model-backed role and `strongest-deviation` has to be made on the drilling-report layer, where the
documents are, and ADR 0008 says so rather than leaving the deferred pass marks pointing at a layer
that cannot settle them.

## What is not here

No correctness figure. Protocol section 18.8 defers it with no threshold invented, because scoring
whether a choke reduction explains a shortfall on a specific North Sea well needs a reader this
project does not have. Section 17 records the same limitation for the cause labels; this is the second
time it has bitten and the protocol states it twice rather than mentioning it once.

What this means concretely: none of the five passing gates can fail because an explanation is wrong.
They can fail because a citation is fabricated, a number is unsourced, a stop condition is misreported,
a trace does not replay, or a finding overclaims its level. Those are real and an implementation can
fail them. Correctness is not among them.

No hold-out investigations. Section 18.9 keeps the hold-out out of this phase, and section 10 scores
it once, in Phase 8.

No value shortfall unless an oil price is passed on the command line. The script computes one only
from a stated assumption, and the finding records the assumption beside the number rather than
presenting a currency figure as a measurement.
