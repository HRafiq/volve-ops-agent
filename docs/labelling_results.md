# Labelling results: the development cause-label set

Regenerate with `python scripts/run_label_scoring.py labels/development_pass1.jsonl`, which writes a
run manifest beside its output. Every figure in this document is printed by that script.

**Read this first.** These labels are produced by a language model, `claude-opus-5`, applying
[`docs/labelling_guide.md`](labelling_guide.md). They are not expert labels. Section 17 of the
[evaluation protocol](eval_protocol.md) records why, protocol amendment 2 suspends the two
cause-attribution pass marks that depend on the labels being right, and amendment 3 records a section
added to the guide after labelling. Nothing below selects an approach, and the code refuses to let
anything do so.

## What was labelled

135 events, the development sample drawn by the stratified rule in protocol section 16 at seed
20261006, over 17 wellbores and 99 drilling reports dated 19 November 1992 to 14 April 2014. No
report in the sample falls after the 25 July 2014 production boundary, which protocol section 16
requires of any labelled event, checked rather than assumed.

The published file is [`labels/development_pass1.jsonl`](../labels/development_pass1.jsonl). Each row
carries the cause, the verbatim span, the precedence rule that settled it, and a note where the call
was close: 55 rows carry a note and 14 of those name a taxonomy label other than the one assigned.

## Section 14.3: both deterministic pass marks pass

| pass mark | result |
|---|---|
| Event detection is exact | **pass**. 617 qualifying blocks across the sample's 99 documents, 617 events, no block dropped, none duplicated, none produced from a block that does not meet the section 14.1 rule. |
| Duration is exact | **pass**. Every stored duration equals its block's own timestamps within one minute. |

These are unaffected by who assigned the causes, which is why protocol section 17 leaves them
gating. The check runs on a walk of the XML written separately from the extractor in
`src/volve_ops/extraction/integrity.py`; re-running the extractor and comparing its output with
itself would have passed by construction. The one thing shared with the extractor is section 14.1's
rule, because that rule is the specification and a second copy would test the copy. Its pairing key,
a block's start time and activity code, is unique across all 1,759 reports in this corpus, and a
collision would surface as a false failure rather than a false pass.

**What passing them does not establish.** They cover which blocks became events and how long each
lasted, and no other field. Both marks can pass while `state_detail`, `subcategory`, `comment`,
`well`, `wellbore` or `report_date` is wrong, and the first two are what the `echo-statedetail`
baseline and the whole cause layer are built from. A comment correctly extracted but attached to the
wrong block would satisfy both marks, and would also satisfy the span gate, which checks a cited span
against the extractor's own comment field rather than against the XML.

## The label distribution

| cause | n | share | in the macro average |
|---|---|---|---|
| `not_stated` | 75 | 55.6% | yes |
| `equipment_failure` | 25 | 18.5% | yes |
| `hole_problem` | 14 | 10.4% | yes |
| `waiting_on_weather` | 8 | 5.9% | yes |
| `other` | 5 | 3.7% | yes |
| `waiting_on_cement` | 3 | 2.2% | no |
| `waiting_on_logistics` | 2 | 1.5% | no |
| `well_control` | 2 | 1.5% | no |
| `human_or_procedural` | 1 | 0.7% | no |
| `equipment_maintenance` | 0 | 0% | unreachable, see below |
| `rig_service` | 0 | 0% | unreachable, see below |
| `cementing_problem` | 0 | 0% | absent |

Five classes clear protocol section 14.5's five-instance floor and enter the macro average. That
number is reported with every macro figure below, because a macro average over five classes and one
over eleven are not comparable and the protocol fixes the rule rather than leaving it to whoever
quotes the number.

`not_stated` at 55.6% is the most important figure here, close to the guide's own advance estimate of
near 60 percent. A system that cannot be scored on its willingness to abstain would be rewarded for
guessing on more than half the sample.

`other` at 3.7% stays well under the one fifth at which the guide condemns the taxonomy rather than
stretching the class. The five are two shifts suspended by an oilfield-services strike, two blocks of
thick mud fouling surface systems, and one wait on a third party commissioning a christmas tree. The
two strike rows are contestable against `waiting_on_logistics`, whose wording names personnel; the
rows say so.

A class absent from the sample is not scored zero, per protocol section 14.5: that would measure the
draw rather than the system.

## Two taxonomy classes turned out to be unreachable

`equipment_maintenance` and `rig_service` have no instances, and that is a defect in the guide rather
than a property of the corpus.

Ten events have comments that are nothing but work on named equipment or a rig operation: "Serviced
TDS", "Function tested Weatherford auto stabber", "Perform slip and cut of drill line", "POOH TO
CHANGE MWD TOOL". The first labelling pass called them `equipment_maintenance` and `rig_service`,
reading precedence rule 3, which presumes those classes are assignable from a comment naming specific
equipment.

Independent review found that wrong, and the labels were changed before any approach was scored.
Precedence rule 1 says an activity description is not a cause and that it "outranks every one below
it", and its own examples are "Installed PS-21 slips", "L/D cutter BHA" and "Performed derrick
inspection", which are exactly these shapes. Every one of the ten spans was the activity description,
which the span convention forbids in the same sentence. All ten are now `not_stated`, tagged
`P1-unreachable` so a reader who prefers the rule-3 reading can find them.

Generalising: **rule 1 makes both classes unreachable**, because any comment that would earn either
is an activity description and rule 1 outranks the rules that would assign them. Three of twelve
taxonomy classes are unused and two of those three are unusable. Fixing rule 1 needs a new guide
version in its own pushed commit, and is not done mid-labelling, because editing a rule while
labelling against it is how a label set comes to describe its own conventions.

This mattered to the published numbers. It changed both baselines' macro-F1, both exact-agreement
rates, the number of classes in the macro average from six to five, and which baseline is the better
one. Protocol amendment 3 records it.

## The two fixed baselines, measured

Both are deterministic tables fixed in protocol section 14.4 before any label existed, and both are
exempt from amendment. They are the only uncontaminated part of this comparison.

| baseline | macro-F1 | classes | exact agreement |
|---|---|---|---|
| `echo-subcategory` | 0.2992 | 5 | 40/135 = 29.6% |
| `echo-statedetail` | **0.3329** | 5 | **74/135 = 54.8%** |

`echo-statedetail` is the better baseline on both metrics, so it is the one to beat, and the
suspended bar would have been 0.3995.

Per class, over the five that enter the average:

| cause | `echo-subcategory` F1 | `echo-statedetail` F1 |
|---|---|---|
| `not_stated` | 0.451 | 0.619 |
| `equipment_failure` | 0.057 | 0.633 |
| `hole_problem` | 0.047 | 0.412 |
| `waiting_on_weather` | 0.941 | 0.000 |
| `other` | 0.000 | 0.000 |

Three things fall out of this table.

`stateDetailActivity` is a genuinely strong free signal for equipment failure, at F1 0.633 from a
lookup with no reading at all. Protocol section 14.4 predicted that when it named both baselines
rather than only the weaker one, and because baselines are exempt from amendment, adding the second
one after seeing this would not have been allowed. This is the number that would have been missing.

`echo-subcategory` is nearly useless on `equipment_failure` and `hole_problem`, at 0.057 and 0.047,
despite its table mapping `repair` to the first and `fish`, `sidetrack` and `lost circulation` to the
second. Its only strength is weather, where the subcategory is the cause. More on why below.

Neither baseline can emit `other` or `waiting_on_cement`, so both score zero on classes worth 3.7%
and 2.2% of the sample. That is a property of the tables, fixed in advance, and not a defect in them.

### A result that did not survive the correction, recorded because it was nearly published

Under the pre-correction labels the two metrics disagreed about which baseline was better:
`echo-statedetail` led on exact agreement, 48.9% against 30.4%, and lost on macro-F1, 0.2655 against
0.3333. That would have been a clean illustration of why a metric must be fixed before the numbers
exist, and this document said so.

It was an artifact. The ten mislabelled events were concentrated in a class only `echo-subcategory`
can emit, which inflated its macro-F1 by giving it a class to be right about. With the labels
corrected, one baseline leads on both metrics and the disagreement is gone. The lesson that remains
is narrower and less flattering: a labelling error inside one class moved a macro average enough to
reverse a published ranking, which is the sensitivity protocol section 14.5's condition 2 exists to
guard against, demonstrated on the labels rather than on a model.

## Where the baselines agree with each other

The two agree on 60 of 135 events, 44.4%. Where they agree, the labels match on 25 of 60. The two
halves of that say different things and an aggregate over them says neither.

**Where both tables abstain**, 44 events, the labels name a cause on 20. That is the behaviour the
labels are supposed to have: reading the comment exists to recover what the structured fields do not
carry. It is also indistinguishable, on this evidence, from a labeller inclined to find causes.

**Where both tables name an actual cause**, 16 events, the labels agree on **one** and call 13 of
them `not_stated`. Those 16 are exactly two shapes: 10 blocks filed `lost circulation` with a
`circulation loss` detail state, and 6 filed `repair` with an `equipment failure` detail state. The
comments on them describe washing, reaming, tripping and circulating, several recording no losses at
all.

One match in 16 is a number to sit with rather than explain away. Either the structured fields are
badly wrong about those events or the labels are, and nothing in this document can say which. An
expert adjudication under protocol section 17.4 is what separates them.

## How far the source's own coding can be trusted

Protocol section 14.6 asks for the rate at which the source's coding disagrees with the comment, and
reports two figures because one of them needs judgement.

**The judgement figure: 21 of 135, 15.6%.** The criterion is in the labelling guide: the subcategory
or detail state names an operation or condition, and the comment neither describes it nor is
consistent with it. Blocks filed `lost circulation` whose text says "NO MUD LOSSES"; blocks filed
`repair` that describe running a tieback sleeve; one filed `lost circulation` whose comment records a
3.5 m3 **gain** with shut-in pressures, which is the opposite condition.

Review found the first pass had applied this inconsistently, including missing that gain, and the
flags were re-applied under the stated criterion. It remains a judgement and is reported as one.

**The mechanical companion: 67 of 135, 49.6%.** The fraction of events where `echo-subcategory` names
a cause that is not the label. It needs no judgement and cannot be applied inconsistently. It is also
confounded, since it moves when the labels are wrong, so it is not a better measure of the source's
coding, only a reproducible one.

Both figures point the same way, and together they are why `echo-subcategory` fails on the two
largest cause classes. Its mapping table is not wrong. The filing is.

## Which rules did the work

Every row records its tag. `P<n>` is the guide's precedence list, `L<n>` its "How to label a cause"
list, because the guide has two numbered lists and a bare `R1` is ambiguous between them.

| applied rule | n | what it is |
|---|---|---|
| `P1` | 46 | `not_stated` wins: the comment describes what was done |
| `taxonomy` | 34 | a direct taxonomy match, no precedence needed |
| `P2` | 22 | `equipment_failure` over maintenance, a fault named |
| `P1-unreachable` | 10 | rule 1 takes from rule 3; the ten contested events above |
| `P1-span` | 7 | a cause is implied but every candidate span is an activity description |
| `P1-monitor` | 4 | a measurement that can read normal is not an attribution |
| `P1-outcome` | 4 | a bare unsuccessful outcome, no fault predicated of anything |
| `P1-total` | 3 | a daily or per-trip tally is reporting, not attribution |
| `P2-test` | 3 | a failed test with a quantified or isolated fault symptom |
| `L2-ambiguous` | 1 | two causes plainly implied, neither chosen by the comment |
| `L4` | 1 | more than one cause; labelled the one it was attributed to |

Seventy-five rows rest on a rule-1 reading of some kind. Of the seven conventions the first pass had
to derive, five only named a rule already in the guide, one changed three labels (`P2-test`), and one
was withdrawn on review (`P1-unreachable`). Protocol amendment 3 separates them, and the guide marks
the whole section as written after labelling rather than before.

## What is not here

No cause-attribution model has been run, so there is nothing to compare with the baselines yet. When
one is, protocol section 17.2 governs what the comparison may claim, and while the suspension holds
no gate can fail for being wrong about a cause.

No inter-pass agreement, withdrawn by protocol amendment 2. No anchoring rate, which needed a human
in the loop that does not exist. No hold-out labels: the four hold-out wells and their fixed budget of
60 events stay unlabelled until the final scoring, per protocol sections 10 and 16.

No expert adjudication, which is the thing that would make the suspended pass marks measurable again.
What exists is the draw: `python scripts/draw_adjudication.py labels/development_pass1.jsonl` writes
protocol section 17.4's 40 events at the pre-registered seed, 20 from the classes the guide predicts
will split two labellers and 20 at random from the rest. The worksheet carries exactly section 14.2's
permitted set and no machine label. Doing the draw before an adjudicator exists is the point, because
a subsample sized or seeded once someone is ready to label it is a subsample chosen after seeing what
it produces. Section 17.4 also fixes which version of the guide an adjudicator is given, since the
current one describes how several of the drawn events were resolved.
