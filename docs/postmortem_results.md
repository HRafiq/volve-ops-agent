# Post-mortem results: where the non-productive time went, and how little of it is characterised

Regenerate with `python scripts/run_postmortem.py data/cache/ddr_xml`. Exit status is the gate. No
model is involved: the post-mortem is an aggregation of the source's own fields.

Protocol section 20 fixed all of this before any of it was built and was pushed as `prereg-v9`, with
every threshold stated rather than left in the source.

## The five gating pass marks

| section 20.6 pass mark | result | what it examined |
|---|---|---|
| Categories reconcile, and the event store agrees | **pass** | 11 wells, to 0.01 hours |
| Every citation resolves | **pass** | 13 of 13 representative spans |
| No hold-out well in the post-mortem or the store | **pass** | 7 wells reported, 4 excluded |
| No currency figure without its assumption | **pass** | no rate supplied, so no figure |
| A hold-out correction is refused at write time | **pass** | probed on `15/9-F-4` every run |

The reconciliation is the one worth describing. The walk in
`src/volve_ops/postmortem/recorded_time.py` goes through the XML independently of the extractor,
sharing only section 14.1's non-productive rule, and its per-well non-productive totals are then
compared against the event store's. That is section 20.8's spot-verification, and it is a real check:
the two paths count the same blocks from the same files by different code, and they agree to within
floating point on all eleven wells.

## Recorded time, in the three categories ADR 0002 fixed

B1 failed, so there is no planned-versus-actual breakdown. ADR 0002 named the substitute, and the word
"productive" is absent on purpose: nothing in this source positively identifies productive work, so
calling the remainder productive would invent a classification the data does not carry.

| category | hours | share |
|---|---:|---:|
| non-NPT recorded time | 30,835 | 78.3% |
| non-productive time | 8,563 | 21.7% |
| other unclassified time | 97.5 | 0.2% |

Across 1,759 reports and 23,447 activity blocks, none of them untimed. Two measurements that are
reported rather than absorbed into a tolerance: the blocks sum to 1.8 hours more than the wall clock
they cover, which is five reports recording two things at once, and 97.5 hours fall between blocks
inside a report, which is the third category above.

## Per well, development only

The drilling corpus covers eleven wells and section 16 holds out four. A post-mortem over all eleven
would mean reading the hold-out before Phase 8, which section 4.3 forbids, so **13.2 percent of the
corpus's non-productive hours are held out and not reported here**. That is the honest cost of the
discipline, stated rather than quietly folded into a total.

| well | reports | NPT hours | non-NPT recorded | NPT share |
|---|---:|---:|---:|---:|
| 15/9-19 | 375 | 3,170 | 5,564 | **36.3%** |
| 15/9-F-11 | 174 | 955 | 2,935 | 24.6% |
| 15/9-F-15 | 292 | 1,232 | 5,181 | 19.2% |
| 15/9-F-1 | 216 | 864 | 4,020 | 17.7% |
| 15/9-F-12 | 165 | 628 | 3,136 | 16.7% |
| 15/9-F-14 | 134 | 449 | 2,497 | 15.2% |
| 15/9-F-10 | 71 | 132 | 1,561 | **7.8%** |
| **development total** | 1,427 | **7,430** | 24,894 | 23.0% |

A 4.6-times spread between the best and worst well. `15/9-19` is the 1990s exploration well and
`15/9-F-10` a 2009 production well, so the spread is as much about two decades of practice and
equipment as about either well. That is a limitation of the comparison, not a finding from it.

## The lessons register

A pattern is a distinct `(activity subcategory, detail state)` pair, taken from the source's own
fields. Grouping by cause label would make the register inherit section 17's limitation, since the
labels are machine-assisted; grouping by what the operator filed carries no such dependency.

**13 recurring patterns of 51, accounting for 6,230 of 7,430 development non-productive hours, 83.9
percent.** The 38 patterns below the thresholds of three wells and twenty-four hours account for 1,200
hours between them. So the time is concentrated: a quarter of the patterns carry five-sixths of the
hours.

| subcategory | detail state | wells | events | hours | labelled |
|---|---|---:|---:|---:|---:|
| waiting on weather | success | 7 | 372 | **1,595** | 2% |
| other | equipment failure | 7 | 635 | 1,309 | 1% |
| other | success | 6 | 257 | 932 | 1% |
| repair | equipment failure | 7 | 406 | 646 | 1% |
| wait | success | 7 | 162 | 364 | 5% |
| maintain | equipment failure | 6 | 139 | 288 | 4% |
| fish | success | 3 | 100 | 268 | 9% |
| repair | success | 6 | 212 | 254 | 0% |
| repair | operation failed | 5 | 74 | 163 | 5% |
| other | operation failed | 7 | 98 | 161 | 3% |
| maintain | success | 7 | 99 | 140 | 4% |
| fish | stuck equipment | 4 | 27 | 72 | 0% |
| rig up/down | equipment failure | 4 | 19 | 39 | 53% |

The largest pattern is weather. 1,595 hours across all seven wells and 372 events, from November 1992
to October 2016, which is 21.5 percent of development non-productive time. Cited verbatim from
`15_9_F_1_B_2013_09_16.xml`: "Waited for weather." No system fixes that, and a lessons register whose
top entry is the North Sea is a useful corrective to the idea that non-productive time is mostly
avoidable.

## The finding that bears on everything else in this project

**The last column.** Across the 13 recurring patterns, **65 of 2,600 events carry a cause label: 2.5
percent.** The largest pattern, 1,595 hours of weather waiting, has 9 labels in 372 events.

This is not a defect in the labelling. It is the measured consequence of a choice made in protocol
section 16 and the labelling guide: the sample is stratified by activity subcategory **so that rare
subcategories appear at all**, because a proportional draw would give `well control`, 29 events in the
whole corpus, a good chance of appearing zero times. Stratification buys per-class scorability and
pays for it in hours covered, and `rig up/down / equipment failure` shows both sides: 19 events, 39
hours, and 53 percent labelled.

So the labelled sample is the right sample for scoring a classifier per class, and close to the wrong
one for explaining where the time went. Both statements are true and the project has only been making
the first one. Nothing in the pre-registration anticipated this, and it is the clearest argument this
project has produced for a second, hours-weighted labelling pass.

## The correction store

Versioned, append-only, and **empty**. Zero corrections across zero versions.

That is not a gap to be filled by me. A correction is a person changing a category, a duration, an
equipment name or a cause text, and the only corrections I could justify would be the 21 events where
the source's subcategory contradicts its own comment, which the labelling guide explicitly reserves as
a data-quality observation that is "reported separately and never used to correct it".

So section 19.2's fourth leakage check, which audits the correction store, **still examines nothing**,
and the harness continues to print it under "checks that examined nothing". Phase 5 was supposed to end
that and has not. What it has done instead is make the refusal demonstrable: every run proposes a
correction against a real hold-out event and confirms the store refuses it before anything touches the
disk, because a store that writes six corrections and raises on the seventh has already leaked the
first six.

The three rules are in place and tested: a hold-out correction refused at write time, a version that
cannot be rewritten, and a correction withheld as a few-shot example from the extraction version that
produced the event it corrects. The last one is half-enforceable, and section 20.5 says which half: the
store can refuse to hand the example over, and it cannot stop a person pasting it into a prompt.

## No currency figure

None is computed, because no day rate was supplied and none is built in. Where one is supplied the
figure is reported as an *estimated rig-time cost equivalent at a stated assumption*, with the
assumption printed beside the number every time it appears.

A rig day rate is a commercial negotiation this project has no access to. Section 20.3's reasoning is
that an illustration which circulates as a finding is the failure mode, and the cheapest way to prevent
it is to make the number impossible to produce without its caveat attached.

## What is deferred

| not measured | why | what would settle it |
|---|---|---|
| Planned versus actual time | B1 failed on coverage, per ADR 0003 | drilling programmes covering three wells' histories, which this dataset lacks |
| Whether a recurring pattern is a correct lesson | needs drilling-operations experience | the section 17.4 adjudication, extended to the register |
| The correction loop's effect on extraction quality | no corrections exist, and no second extraction version | corrections from a person, then a scored second version with section 20.5's leakage rule observed |
