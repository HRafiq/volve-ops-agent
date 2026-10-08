# Post-mortem results: where the non-productive time went, and how little of it is characterised

Regenerate with `python scripts/run_postmortem.py data/cache/ddr_xml`. Exit status is the gate. No
model is involved: the post-mortem is an aggregation of the source's own fields.

Protocol section 20 fixed all of this before any of it was built and was pushed as `prereg-v9`. Two
amendments then changed it after the first run, both prompted by independent review, both labelled as
post-inspection. Amendment 7 corrected three pass marks that could not fail, one pre-registered mark that
had been dropped without an amendment, and five holes in the correction store. **Amendment 8 is about
amendment 7**: a second review checked its claims against the code and three did not hold, and a third
review of amendment 8's own fixes found three more. The manifest records `protocol_version: v11`, and
there is no `prereg-v10` tag because v10 was written and never pushed.

That sequence is the most useful thing in this document, so it is stated before any figure. The first
review found gates that could not fail. The resolution of that review contained gates that could not
fail. The resolution of *that* contained one more, and an overclaim that had been retracted in two files
and rewritten into two others, with a fifth instance standing in an ADR none of the first three rounds
looked at. An amendment is a claim about a repository and is exactly as checkable as any
figure in it, which means writing one in the same session as its own fixes is the project's recurring
defect at one level up.

## The seven gating pass marks

Section 20.6 pre-registered six. The first implementation carried five, and the first version of this
document was headed "The five gating pass marks" with the count rewritten around the drop. Register
reproducibility was the missing one. It is implemented, and a seventh was added because review ran the
whole harness against an empty directory and every mark passed with exit zero.

| section 20.6 pass mark | result | what it examined |
|---|---|---|
| 0. The corpus is not empty | **pass** | 11 walked wells, 3,673 stored events, 13 patterns |
| 1. Categories reconcile, and the event store agrees | **pass** | 11 wells, on hours to 0.01 and on block counts |
| 2. Every citation resolves | **pass** | all 51 published citations, recurring and excluded |
| 3. No hold-out well in anything published | **pass** | 182 well mentions across both pattern tables and the per-well table |
| 4. No currency figure without its assumption | **pass** | nothing: no rate supplied, so no figure |
| 5. The register is reproducible | **pass** | 765 citation fields, 15 for each of 51 patterns |
| 6. A hold-out correction is refused at write time | **pass** | 7 synthetic probes: five that must be refused, one that must be accepted, one name check |

Mark 4 examined nothing, and the harness prints it under "gates that examined nothing, and so
demonstrate nothing". A gate that passes over an empty set has demonstrated nothing, which is why every
gate reports what it looked at next to its verdict.

### Seven defects over four rounds, six of them checks that could not fail

Three were found by the first review, two by a second review of the first one's fixes, one by a third
review of the second one's, and one by a fourth. Five of the seven gates are in the table; the write-time
refusal appears twice, and the last row is not a gate defect but a measurement of the guard the gate
checks. The shape is five phases old and the diagnosis has not changed: each gate defect was an expression
in `scripts/run_postmortem.py`, the one file with no test, written in the same sitting as the thing it
checked.

| round | mark | how it could not fail | what it does now |
|---|---|---|---|
| 1 | Reconciliation | compared the two categories against a property defined as their sum, so it computed `abs(x - x)`; its test was the same expression | compares them against a total taken from the block list, and compares hours **and** block counts against the event store |
| 1 | Hold-out containment | read the development-well list that had just been passed into the register, so it tested the negation of its own filter | reads the register's output, recurring and excluded patterns alike |
| 1 | Currency | asked the producing function whether it had produced a string, which both its branches do | reads the published artifact and refuses a non-finite figure or a non-positive rate |
| 2 | Register reproducibility | rebuilt the register over reversed input and compared four fields; every sort key is tie-broken by a unique id, so no permutation can change the output | compares every field of every citation against the register being published, built with the same label and miscoding sets |
| 2 | Write-time refusal | the event-to-well mapping the refusal depends on was an optional argument, and no caller supplied it, so only the forgeable fallback ran | the argument is required, and an event the store cannot place is refused rather than trusted |
| 3 | Write-time refusal, again | the probe that had to be **accepted** never called `write`; it asked `is_hold_out` about a string, so a store that refused everything passed | every probe writes, to a throwaway directory, and the gate examines seven things |
| 4 | The refusal itself, not the gate | the text scan meant to catch a pasted hold-out comment matches a well name, and only 18 of this corpus's 616 hold-out comments contain one | a correction whose old value is not what the record says for that event is refused, which catches all 616 |

How each was demonstrated rather than argued. The fourth: 4,000 adversarial inputs, duplicate ids and tied
durations included, and no failing case. The fifth: re-running the first review's own attack against the
default call, where a correction carrying a hold-out event id, a development well and the hold-out event's
verbatim comment wrote cleanly, past a fix the amendment said had closed it. The sixth: a
`CorrectionStore` subclass whose `write` raises unconditionally, which the gate approved. The seventh is
not a gate defect but a measurement, and it is the most useful of the four rounds: the text scan was
counted against the real corpus, where it catches 18 of 616 hold-out comments, because a report about a
well mostly does not name the well.

The guard around the correction store was wrong in all four rounds, which is worth saying plainly. It is
the only check here that has to **construct** its own evidence rather than read an artifact, and
constructing a situation is where you get to choose what not to construct. Four of the six gate defects
reduce to one sentence: the check asked a question of the wrong object.

All seven marks are now functions in `src/volve_ops/postmortem/gates.py`, each with a test that makes it
fail, and the gate names live in one tuple that the results table imports rather than retypes.

### What the reconciliation actually establishes

Less than the first two versions of this document claimed, and worth separating.

The first comparison, the two categories against the block total, has both sides subtracting the same
pair of timestamps. No input can make it disagree about a duration: measured across all eleven wells the
worst error is 3.64e-12 against a tolerance of 0.01, and was 4.09e-12 under the implementation this one
replaced, which is the same statement about float association rather than a figure that moved for a
reason. What it does establish is that the two categories
**partition** the timed blocks, each duration counted once rather than twice or never.

The second and third comparisons are the real ones. The walk in
`src/volve_ops/postmortem/recorded_time.py` goes through the XML and the extractor goes through it
separately, and their per-well non-productive hours and block counts are compared. That is section
20.8's spot-verification. It is a **second** path rather than an independent one, and the difference
matters enough to state: the walk shares six functions with the extractor (`WITSML_NS`,
`is_non_productive`, `parse_report_filename`, `parse_xml_file`, `well_of`, `canonical_from_ddr_token`)
and traverses `drillReport` then `activity` the same way. `is_non_productive` is shared deliberately,
because section 14.1's rule is the specification and a second copy of it would test the copy. So what
agrees is the per-block arithmetic, the category branch, the aggregation and the store write; a defect
inside one of the six shared functions would be invisible here, and section 14.3 covers the shared
traversal against the source instead.

## Recorded time, in the three categories ADR 0002 fixed

B1 failed, so there is no planned-versus-actual breakdown. ADR 0002 named the substitute, and the word
"productive" is absent on purpose: nothing in this source positively identifies productive work, so
calling the remainder productive would invent a classification the data does not carry.

Hours exactly as the manifest records them, because 8,563.25 rounded to one decimal place is 8,563.2
or 8,563.3 depending on the rounding rule, and a reader reconciling a document against a manifest should
not have to work out which one was used.

| category | hours | share of recorded time |
|---|---:|---:|
| non-NPT recorded time | 30,834.73 | 78.1% |
| non-productive time | 8,563.25 | 21.7% |
| other unclassified time | 97.50 | 0.2% |
| **total recorded** | **39,495.48** | **100.0%** |

Across 1,759 reports and 23,447 activity blocks, none of them untimed. Two measurements that are
reported rather than absorbed into a tolerance: the blocks sum to 1.8 hours more than the wall clock
they cover, which is a few reports recording two things at once, and 97.5 hours fall between blocks
inside a report, which is the third category above.

## Per well, development only

The drilling corpus covers eleven wells and section 16 holds out four. A post-mortem over all eleven
would mean reading the hold-out before Phase 8, which section 4.3 forbids, so **13.2 percent of the
corpus's non-productive hours are held out and not reported here**. That is the cost of the discipline,
stated rather than quietly folded into a total.

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

A 4.7-times spread between the best and worst well, 36.29 percent against 7.80. `15/9-19` is the 1990s exploration well and
`15/9-F-10` a 2009 production well, so the spread is as much about two decades of practice and
equipment as about either well. That is a limitation of the comparison, not a finding from it.

## The lessons register

A pattern is a distinct `(activity subcategory, detail state)` pair, taken from the source's own
fields. Grouping by cause label would make the register inherit section 17's limitation, since the
labels are machine-assisted; grouping by what the operator filed carries no such dependency.

**13 recurring patterns of 51, accounting for 6,230.5 of 7,430.3 development non-productive hours, 83.9
percent.** The 38 patterns below the thresholds of three wells and twenty-four hours account for 1,199.8
hours between them. So the time is concentrated: a quarter of the patterns carry five-sixths of the
hours.

| subcategory | detail state | wells | events | hours | labelled | mis-filed |
|---|---|---:|---:|---:|---:|---:|
| waiting on weather | success | 7 | 372 | 1,595 | 9 of 372 | 1 of 9 |
| other | equipment failure | 7 | 635 | 1,309 | 5 of 635 | 0 of 5 |
| other | success | 6 | 257 | 932 | 2 of 257 | 0 of 2 |
| repair | equipment failure | 7 | 406 | 646 | 6 of 406 | **5 of 6** |
| wait | success | 7 | 162 | 364 | 8 of 162 | 0 of 8 |
| maintain | equipment failure | 6 | 139 | 288 | 5 of 139 | 1 of 5 |
| fish | success | 3 | 100 | 268 | 9 of 100 | 0 of 9 |
| repair | success | 6 | 212 | 254 | 0 of 212 | - |
| repair | operation failed | 5 | 74 | 163 | 4 of 74 | 2 of 4 |
| other | operation failed | 7 | 98 | 161 | 3 of 98 | 0 of 3 |
| maintain | success | 7 | 99 | 140 | 4 of 99 | 0 of 4 |
| fish | stuck equipment | 4 | 27 | 72 | 0 of 27 | - |
| rig up/down | equipment failure | 4 | 19 | 39 | 10 of 19 | 1 of 10 |

The largest pattern is weather. 1,595 hours across all seven wells and 372 events, from November 1992
to October 2016, which is 21.5 percent of development non-productive time. Cited verbatim from
`15_9_F_1_B_2013_09_16.xml`: "Waited for weather." No system fixes that, and a lessons register whose
top entry is the North Sea is a useful corrective to the idea that non-productive time is mostly
avoidable.

The mis-filed column counts events where the source's own subcategory contradicts its own comment, as
recorded during labelling and never used to correct anything. It is only countable where a label exists,
so every figure in it has the sample's denominator and not the pattern's. On that basis `repair /
equipment failure` is the pattern to distrust: 5 of its 6 labelled events read as something other than
an equipment repair. The register reports it as it is filed, because reporting the record is what the
register is for, and the column is the warning attached.

## The patterns the thresholds exclude

The thresholds are three wells and twenty-four hours, fixed in section 20.4 before the register was
built. The first version of this document gave only the total, "38 patterns, 1,199.8 hours", because what
a threshold excludes is part of what the threshold means and the names it excluded were inconvenient.

The ten largest by hours, which is what the harness prints every run. All 38 are in
`data/cache/postmortem_run.json` under `excluded_pattern_detail`, each with its own citation, and the
cutoff is stated because the first version of this table stopped at eight, one row above the only large
pattern the **hours** bar excludes rather than the well count.

| subcategory | detail state | wells | events | hours | first seen | last seen |
|---|---|---:|---:|---:|---|---|
| sidetrack | success | 1 | 185 | 562 | 1992-12-13 | 1997-07-30 |
| lost circulation | circulation loss | 1 | 58 | 118 | 1992-12-14 | 1997-11-27 |
| fish | operation failed | 2 | 28 | 82 | 1993-04-08 | 2013-03-13 |
| casing | success | 1 | 24 | 64 | 1997-09-01 | 1997-12-15 |
| well control | circulation loss | 1 | 23 | 49 | 2008-11-15 | 2008-11-18 |
| lost circulation | success | 2 | 17 | 43 | 1992-12-25 | 2016-08-14 |
| casing | operation failed | 1 | 16 | 39 | 1992-11-27 | 1997-12-13 |
| waiting on weather | circulation loss | 1 | 2 | 24 | 1997-11-20 | 1997-11-21 |
| maintain | operation failed | **5** | 13 | 23.75 | 1993-01-27 | 2013-05-16 |
| sidetrack | equipment failure | 1 | 12 | 22.5 | 1992-12-18 | 1993-01-07 |

`maintain / operation failed` is the row worth noticing. Five wells, so it clears the well bar, and 23.75
hours against a 24-hour floor: it misses by fifteen minutes. That is what a fixed threshold looks like
from the inside, and it is reported rather than rounded, because 24 hours was written down in section
20.4 before the register was built and a bar that bends for a quarter of an hour is not a bar.

These are the names an operations reader would look for first: sidetracks, lost circulation, well
control, casing. All of them are excluded, and the three-well bar is what excludes them, not their size.
32 of the 38 excluded patterns occurred on a single well and they hold 1,023 of the 1,199.8 excluded
hours, 85 percent, so the bar that excludes them is the well count and not the hours. Dropping it to two
wells would admit two patterns and 125 hours. The largest exclusion, 562 hours of sidetrack time on
`15/9-19`, is 7.6 percent of development non-productive hours on its own; admitted to the register it
would rank fifth, just below `repair / equipment failure`.

A single-well event cannot appear in the register however expensive it was. That is the intended
behaviour of a cross-well register and it is also its sharpest limitation, because the most expensive
things that happen on a drilling rig tend to happen once. The harness prints the sentence under the
table every run.

## The finding that bears on everything else in this project

**Across the 13 recurring patterns, 65 of 2,600 events carry a cause label: 2.5 percent.** The largest
pattern, 1,595 hours of weather waiting, has 9 labels in 372 events.

This is not a defect in the labelling. It is the measured consequence of a choice made in protocol
section 16 and the labelling guide: the sample is stratified by activity subcategory **so that rare
subcategories appear at all**, because a proportional draw would give `well control`, 29 events in the
whole corpus, a good chance of appearing zero times. Stratification buys per-class scorability and pays
for it in hours covered, and `rig up/down / equipment failure` shows both sides: 19 events, 39 hours,
and 10 of 19 labelled.

So the labelled sample is the right sample for scoring a classifier per class, and close to the wrong
one for explaining where the time went. Both statements are true and the project has only been making
the first one. Nothing in the pre-registration anticipated this, and it is the clearest argument this
project has produced for a second, hours-weighted labelling pass.

## The correction store

Versioned, append-only, and **empty**. Zero corrections across zero versions.

That is not a gap to be filled by me. A correction is a person changing a category, a duration, an
equipment name or a cause text, and the only corrections I could justify would be the events where the
source's subcategory contradicts its own comment, which the labelling guide explicitly reserves as a
data-quality observation that is "reported separately and never used to correct it". The mis-filed
column above is that observation, kept where it belongs.

So section 19.2's fourth leakage check, which audits the correction store, **still examines nothing**,
and the evaluation harness continues to print it under "checks that examined nothing". Phase 5 was
supposed to end that and has not. What it has done instead is make the refusal demonstrable: every run
proposes a synthetic correction against a hold-out event and confirms the store refuses it before
anything touches the disk, because a store that writes six corrections and raises on the seventh has
already leaked the first six.

The three rules are in place and tested, and review found five ways around the first one before they
were closed:

1. **A hold-out correction is refused at write time.** The refusal filtered on the well recorded on the
   correction rather than the well of the event it names, so a correction carrying a hold-out event id, a
   development well and the hold-out event's verbatim comment wrote cleanly. `write` now resolves the
   event and refuses a correction whose well disagrees with its event's. `is_hold_out` also claimed to
   fail closed and failed open on `15/9-f-4`, on the NPD spelling `NO 15/9-F-4` and on `15 / 9-F-4`; it
   now normalises, retries, and refuses what it still cannot place.
2. **A version cannot be rewritten.** The write is `open(path, "x")`, so the filesystem enforces it. The
   earlier test of `exists() and read_text().strip()` let an empty version be created and then filled,
   which would let a run cite a version that held nothing when it was cited. Version names are now
   validated too, because a name could otherwise escape the store directory to somewhere `versions()`
   could not glob and the audit could not read.
3. **A correction is withheld as a few-shot example from the extraction version that produced the event
   it corrects.** This is half-enforceable and section 20.5 says which half: the store can refuse to hand
   the example over, and it cannot stop a person pasting it into a prompt. The first implementation
   compared versions for inequality rather than order, so a correction made against `extractor-v3` was
   served to `extractor-v0`.

## No currency figure

None is computed, because no day rate was supplied and none is built in. Where one is supplied the
figure is reported as an *estimated rig-time cost equivalent at a stated assumption*, with the
assumption printed beside the number every time it appears, and a non-finite figure or a non-positive
rate is refused.

A rig day rate is a commercial negotiation this project has no access to. Section 20.3's reasoning is
that an illustration which circulates as a finding is the failure mode, and the cheapest way to prevent
it is to make the number impossible to produce without its caveat attached.

## What is deferred

| not measured | why | what would settle it |
|---|---|---|
| Planned versus actual time | B1 failed on coverage, per ADR 0003 | drilling programmes covering three wells' histories, which this dataset lacks |
| Whether a recurring pattern is a correct lesson | needs drilling-operations experience | the section 17.4 adjudication, extended to the register |
| The correction loop's effect on extraction quality | no corrections exist, and no second extraction version | corrections from a person, then a scored second version with section 20.5's leakage rule observed |
| What the single-well patterns cost | the three-well bar excludes them by design | a per-well post-mortem, which is a different artifact from a cross-well register |
