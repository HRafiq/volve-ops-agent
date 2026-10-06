# Labelling guide: non-productive time and its causes

Written before any label is made, and pushed before any extraction is run. That ordering is the
only thing that makes the resulting metrics worth reading: a guide written while looking at
model output describes the output rather than the task.

One person labels this corpus, which is a real limitation and is stated wherever the resulting
figures appear. A re-labelled subsample estimates how consistent that person is with themselves,
which is the floor on what any agreement figure can mean.

## What is being labelled

Activity blocks inside WITSML drill reports. Each block already carries start and end timestamps,
a two-level activity code, a state, and a free-text comment written by whoever filled in the
report at the time.

The labeller does **not** assign the category or the duration. Those come from the source's own
fields, deterministically, and relabelling them would measure the operator's coding from a decade
ago rather than this system's extraction. The labeller records whether the source's own coding
looks wrong, which is a data-quality observation reported separately and never used to correct it.

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

## Consistency

After the main pass, 40 of the labelled events are re-labelled without reference to the first
pass, at least a week later. Twenty is too few: at a `not_stated` rate near 60 percent the
agreement estimate's interval would be roughly plus or minus 20 points, wide enough to be
consistent with both "excellent" and "marginal", and it is asked to serve as the ceiling on what
agreement with the system could mean.

Half the re-labelled subsample is drawn deliberately from events whose first-pass label was
`equipment_failure`, `equipment_maintenance` or `rig_service`, because that is where the
disagreement will be and a random draw would give it two or three instances.

**Pass one is the label set.** Pass two is used only to estimate agreement, never to correct
pass one. Letting the later pass overwrite the earlier makes the reported agreement figure
describe something other than the labels actually used, and a week of labelling drifts a
person's conventions in exactly the direction that would flatter the estimate.

Disagreements are recorded with both labels and the rule, if any, that would have settled them.
A pair that no rule in this guide resolves is a defect in the guide.

## What is recorded per event

```
event_id, source_document, activity_code, state,
cause, evidence_span, cause_notes,
source_coding_looks_wrong (bool), labeller_pass, labelled_at
```

No field here is a confidence score. A labeller's confidence in their own judgement is not
evidence about the system, and recording it invites it to be used as one.
