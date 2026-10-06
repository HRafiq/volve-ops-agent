# Labelling guide: non-productive time and its causes

Written before any label is made, and pushed before any extraction is run. That ordering is the
only thing that makes the resulting metrics worth reading: a guide written while looking at
model output describes the output rather than the task.

**The labels are produced by a language model, not by a domain expert.** Section 17 of the
evaluation protocol records why, what it costs, and the adjudication that would restore the pass
marks it suspends. Read that section before any figure here. The short version: the project's
author cannot assign a cause to a 1997 drilling comment, labelling anyway would have put a
human's name on a non-expert's judgement, and the alternative taken was to label by model, say
so, and withdraw the pass marks that depend on the labels being right.

Everything below about how to label was written before any label was made, **except** the section
"Conventions the first pass had to settle", which is dated and marked as what it is: a product of
the first pass, written afterwards. Protocol amendment 3 records that, because this guide is
load-bearing for two of the protocol's pass marks and a section added to it after labelling is a
change to a pre-registered document rather than a footnote on one.

The rest turned out to be the specification a model was held to rather than a person, which changes
who applies the rules and not what the rules are.

## What is being labelled

Activity blocks inside WITSML drill reports. Each block already carries start and end timestamps,
a two-level activity code, a state, and a free-text comment written by whoever filled in the
report at the time.

The labeller does **not** assign the category or the duration. Those come from the source's own
fields, deterministically, and relabelling them would measure the operator's coding from a decade
ago rather than this system's extraction. The labeller records whether the source's own coding
looks wrong, which is a data-quality observation reported separately and never used to correct it.

The criterion for that flag, stated because the first pass applied it inconsistently and the
inconsistency was found in review: **flag the block when its subcategory or detail state names an
operation or a condition, and the comment neither describes it nor is consistent with it.** A block
filed `lost circulation` whose comment records a gain is flagged. A block filed `fish` whose comment
describes part of a fishing job is not. Applying this needs a reading of the comment, so it is a
judgement, and protocol section 14.6 reports it beside a mechanical companion that needs none.

What the labeller does assign is the **cause**, and the span of text supporting it.

## The cause taxonomy

Fixed here, before any comment is read in bulk. Causes that genuinely do not fit become
`other`, and if `other` exceeds a fifth of labelled events the taxonomy is wrong and is revised
in a new protocol version rather than stretched.

| cause | what it covers |
|---|---|
| `equipment_failure` | A named piece of equipment stopped working: pump, motor, sensor, valve, BOP, top drive. |
| `equipment_maintenance` | Planned or corrective work on equipment that was not broken mid-operation. |
| `hole_problem` | Stuck pipe, pack-off, tight hole, losses, influx, wellbore instability. |
| `cementing_problem` | Cement job quality, placement, or remediation. |
| `waiting_on_weather` | Operations suspended for sea state, wind or visibility. |
| `waiting_on_logistics` | Waiting for materials, personnel, boat or helicopter. |
| `waiting_on_cement` | Waiting on cement to set. Routine, not a problem, and common enough to need its own label rather than falling into `other`. |
| `rig_service` | Rig moves, slips and cuts, routine rig operations that stopped progress. |
| `well_control` | Kick, shut-in, circulation of influx, pressure control. |
| `human_or_procedural` | A procedure done wrong or out of order, where the comment says so. |
| `other` | Genuinely none of the above, with a note saying what it was. |
| `not_stated` | The comment does not say what caused the interruption. |

`not_stated` is not a failure of labelling. It is the single most important label in this guide,
because an extraction system that cannot be scored on its willingness to say nothing will be
rewarded for guessing.

## How to label a cause

1. Read only the comment on the block, plus the block's own activity code, state, detail state
   and timestamps. Do not read the neighbouring blocks, the rest of the report, or any other
   source. That set is exactly what the model is given, which section 14.2 of the evaluation
   protocol pins, and a label made with more context than the system gets measures the wrong
   thing.

   If the comment points somewhere else, as in "SEE GENERAL REMARKS", treat the referenced
   material as absent and label the comment as it stands. Following the pointer would give the
   labeller evidence the model will never have.
2. If the comment states or plainly implies a cause, assign it and mark the span.
3. If the comment describes only *what was done* and not *why*, label `not_stated`. "POOH",
   "Fill pipe", "RIH on 5 1/2 DP" are activities, not causes.
4. If the comment names more than one cause, label the one the interruption is attributed to,
   and note the other. Do not split the event.
5. If the comment contradicts the source's category, label the cause as written and flag the
   disagreement. The comment is the evidence; the code is the operator's filing.

### Precedence, for the pairs that will otherwise split two labellers

These three collide constantly, and the definitions alone will not separate them, so the order
is fixed rather than left to judgement.

1. **`not_stated` wins** unless the comment gives a reason. An activity description is not a
   cause. "Installed PS-21 slips", "L/D cutter BHA", "Performed derrick inspection" are what was
   done. This rule outranks every one below it.
2. **`equipment_failure` beats `equipment_maintenance`** whenever the comment names a fault,
   leak, break or malfunction, regardless of whether the verb is "repaired" or "serviced".
   "Repaired leak on aft PRS" is a failure: a leak is the fault, and repairing it is the
   response.
3. **`equipment_maintenance` beats `rig_service`** when the comment names a specific piece of
   equipment. `rig_service` is for rig-level operations with no equipment named: rig moves,
   slips and cuts.
4. Do not use the block's detail state to break a tie. It says `equipment failure` on 1,535
   blocks including many whose comment mentions no equipment at all, and two of the baselines
   are built from it. A labeller who leans on it is labelling the baseline's answer.

## How to mark an evidence span

The span is a **verbatim substring** of the comment, copied exactly, including its original
casing and spelling. Not a paraphrase and not a tidied version.

Mark the shortest span that supports the cause on its own, under this convention, because
"shortest" alone has no tie-break and the span is otherwise a second axis of disagreement:

- include the causal connective when the comment has one, so "due to sensor problem" rather
  than "sensor problem";
- where there is no connective, take the minimal noun phrase together with its fault word, so
  "leak on aft PRS" rather than "leak" or "aft PRS";
- exclude the surrounding activity description, so not the whole sentence.

For "Change to use only triptank 2 due to sensor problem" the span is "due to sensor problem".
Not "sensor", which names a thing and not a fault, and not the whole sentence, which is mostly
about what was done.

If no substring supports the cause, the cause is `not_stated` by definition. A cause without a
span is the thing this project exists to prevent.

## Sample selection

Drawn from development wells only, per section 16 of the evaluation protocol. The four hold-out
wells are not labelled until the final scoring.

The sample is drawn at random from non-productive blocks, as section 14.1 of the protocol
defines them, stratified by activity subcategory so
that rare subcategories appear, with a target of 120 to 150 events. Random rather than chosen:
picking interesting comments to label produces a benchmark of interesting comments.

No interruption block in this corpus has an empty comment, so there is no empty-comment rule to
make. What there is instead: 31 comments under 15 characters and 237 under 30. Those are
included, and most will be `not_stated`. Excluding short comments would remove exactly the cases
where a system is most tempted to invent something.

## Consistency, and what replaced it

This section used to specify a second pass a week later, by the same person, over 40 of the
labelled events, to estimate how consistent that person is with themselves. That estimate was
going to be the ceiling on what agreement between the system and the labels could mean.

It does not survive the labels being model-produced. Re-running a model over the same comments
measures whether the procedure is stable, which is worth knowing and is not the same quantity.
Reporting it under the old heading would be a borrowed figure, so protocol amendment 2 withdraws
inter-pass agreement from the reported list.

The 40-event subsample survives, with a different job. Protocol section 17.4 hands it to a reader
with drilling-operations experience, who sees the comment and the structured fields but neither
the machine label nor the baselines' predictions. The draw is the one specified here: half from
events labelled `equipment_failure`, `equipment_maintenance` or `rig_service`, where this guide
predicts disagreement, half at random from the rest. Agreement of at least 80 percent restores
the suspended pass marks. Below that the label set is republished as a convention-conformance set
and no approach is selected.

**Pass one is the label set**, unchanged. Nothing from a later pass or an adjudication corrects
it. A label set edited after it was scored against describes something other than the labels the
figures were computed from.

Disagreements are recorded with both labels and the rule, if any, that would have settled them.
A pair that no rule in this guide resolves is a defect in the guide, and section "Conventions the
first pass had to settle" below lists the ones the first pass found.

## Conventions the first pass had to settle

**Added 2026-10-06, after the first pass, and recorded in protocol amendment 3.** Everything else in
this guide predates any label. This section does not, and two of the items below changed labels
rather than merely naming a rule that was already here. A reader weighing the published figures
should treat the section as post-hoc and discount it accordingly, which is why it says so rather
than sitting quietly among the rules it was derived from.

Each convention names the rule it comes from. Tags name their list, because this guide has two
numbered lists: `P<n>` is the Precedence list below, `L<n>` is the "How to label a cause" list above
it. Every label records its tag in `applied_rule`.

1. **`P1-span`: if the only candidate span is an activity description, the label is `not_stated`.**
   From the span convention, which excludes the surrounding activity description. Running an
   overshot implies a fish and pumping an LCM pill implies losses, but neither comment contains a
   span that supports the cause without being the activity itself. 7 events. Names an existing rule;
   changed no label that rule 1 would not already have decided.

2. **`L2-ambiguous`: where the comment plainly implies two causes and chooses neither, the label is
   `not_stated`.** From rule 2's "plainly implies", which requires one cause rather than a
   shortlist. 1 event: a mill making no progress through a window, which is consistent with a worn
   mill and with hard casing. Names an existing rule.

3. **`P1-outcome` and `P2`: a fault word predicated of named equipment is `equipment_failure`; a
   bare statement that an attempt did not succeed is not.** From precedence rule 2, which gates
   failure on a named fault. "perforating gun assembly no. 6 mis-run" names a fault of a named tool.
   "DIDN'T RECOVER SEAL ASSEMBLY" names an outcome, and goes to `not_stated` under rule 1: 4 events.
   Names an existing rule.

4. **`P2-test`: a failed pressure or function test with a quantified fault symptom, or with repeated
   negatives isolated to one named component while another tests good, plainly implies a leak or a
   component failure.** 3 events. **This one changed labels**: the narrowest reading of convention 3
   would have left all three `not_stated`, and they are now in `equipment_failure`, the
   second-largest class. The distinguishing feature is the isolation, not the negative result.

5. **`P1-total`: a daily or per-trip total is reporting, not attribution for the block.** "TOTAL MUD
   LOST TODAY - 11 M3" appears on blocks whose own text says nothing about losses, and one says "NO
   MUD LOSSES" outright. 3 events. Names an existing rule.

6. **`P1-monitor`: a measurement that can read normal is not an attribution; a figure naming an
   abnormal condition is.** Gas percentage, ECD, standpipe pressure and a torque reading inside the
   working range are monitoring. "Had 0.5 m3/hr losses" names a loss. 4 events. Names an existing
   rule.

7. **Withdrawn. `P1-unreachable`, and the defect it exposes.**

   The first pass labelled 10 events `equipment_maintenance` or `rig_service` whose entire comment
   is work on named equipment or a rig operation: "Serviced TDS", "Function tested Weatherford auto
   stabber", "Perform slip and cut of drill line", "POOH TO CHANGE MWD TOOL". It justified that by
   reading precedence rule 3, which presumes `equipment_maintenance` is assignable from a comment
   naming specific equipment.

   **That was wrong and the labels have been changed.** Precedence rule 1 says an activity
   description is not a cause and that it "outranks every one below it", and its own examples are
   "Installed PS-21 slips", "L/D cutter BHA" and "Performed derrick inspection", which are exactly
   these shapes. Every one of the 10 spans was the activity description, which the span convention
   forbids in the same breath. The first pass had the guide's top-ranked rule pointing one way and
   invented a convention pointing the other.

   All 10 are now `not_stated`, tagged `P1-unreachable` so a reader who prefers the rule-3 reading
   can find them without re-deriving which they were.

   **The defect this exposes is in the guide, not in the labels.** Rule 1 as written makes
   `equipment_maintenance` and `rig_service` unreachable: any comment that would earn either is an
   activity description, and rule 1 outranks the rules that would assign them. Both classes are
   consequently absent from the labelled sample, alongside `cementing_problem`, which simply did not
   occur. Three of twelve taxonomy classes are unused, and two of those three are unusable.

   Fixing rule 1 is deferred to the next version of this guide rather than done here. Editing a rule
   while labelling against it is how a label set comes to describe its own conventions, and the
   right place to decide whether maintenance time should be a cause at all is a protocol version
   with its own pushed commit.

   The narrower defect underneath, also left: rule 2 gates `equipment_failure` on a named fault, so
   "Repaired flowline isolation valve" names no fault and falls through. Under rule 1 it now reaches
   `not_stated` anyway, so the gate no longer decides anything in this sample, but the wording is
   still wrong.

## What is recorded per event

```
event_id, source_document, activity_code, state,
cause, evidence_span, cause_notes,
source_coding_looks_wrong (bool), labeller_pass, labelled_at,
label_source, labeller, applied_rule
```

`label_source` is `machine_assisted` on every row of the published set, and `expert` is reserved
for an adjudication under protocol section 17.4. `labeller` names the model or person. Both exist
so that a reader never has to infer provenance from surrounding prose, and so that a later mixed
set cannot quietly present one kind of label as the other.

No field here is a confidence score. A labeller's confidence in their own judgement is not
evidence about the system, and recording it invites it to be used as one. That holds with more
force for a model, whose stated confidence would be the easiest number in the project to mistake
for a calibrated one.
