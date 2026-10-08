# ADR 0007: cause labels are machine-assisted, and the pass marks that need expert labels are suspended

Date: 2026-10-06
Status: accepted

## Context

Section 14 of the evaluation protocol judges cause attribution against a labelled sample of
drilling-report comments, and `docs/labelling_guide.md` was written and pushed before any label
was made. Both assume a human labeller. The guide says so in its second paragraph, and the
protocol's reported-without-a-pass-mark list included inter-pass agreement, which only means
something for a person labelling the same events twice.

The sample was drawn and the guide was fixed. Then the labelling could not proceed as designed.
This project's author does not have drilling-operations experience and cannot say whether
"ATTEMPTED TO ENGAGE SEAL ASSY, NO GO" names an equipment failure, a hole condition, or neither.
That is not a gap that reading the guide closes: the guide fixes the taxonomy and the precedence
rules, and still leaves the judgement about the well to the labeller.

Three routes were open.

**Label anyway.** The author assigns causes, the file says `expert`, and the figures carry a
human's provenance. This is the worst of the three and it is worth naming why: the label set
would be no more accurate than a model's, and the provenance would invite exactly the confidence
it cannot support. A reader discounts a model label. A reader does not discount a human one.

**Engage a domain reviewer.** The right answer, and unavailable for this phase.

**Label by model, declare it, and withdraw the pass marks that depend on the labels being
right.** Taken.

## Decision

The 135 development labels are produced by `claude-opus-5` applying the labelling guide. Every
row of `labels/development_pass1.jsonl` carries `label_source: machine_assisted` and the model
name. The file is published in full, with the applied precedence rule on every row.

Protocol section 17 records this, and protocol amendment 2 suspends section 14.5's conditions 1
and 2 as selection gates. They are still computed and still reported. What they lose is the
authority to select an approach, because an extraction model scored against model labels is being
compared with a labeller of its own kind, and agreement cannot be separated from shared
convention.

The suspension is enforced in code. `LabelledEvent` requires a `LabelSource` with no default,
`selection_permitted` is false if a single label is machine-assisted, and `evaluate` returns
conditions 1 and 2 with `gates=False` and a detail string saying why.

A `gates` flag alone was not enough, and the first version of this decision overstated what it did.
The aggregation a caller writes by hand, `all(r.passed for r in results if r.gates)`, silently turns
a four-condition bar into a two-condition one, and both survivors are conditions an approach controls
unilaterally: condition 3 is satisfied by copying a substring, condition 4 compares the approach with
itself. So `approach_is_selected` is now the only path to saying an approach passed, and it returns
false whenever **any** condition is suspended. A two-condition bar made of self-checks is not a weaker
bar; it is not a bar.

Stated plainly, because it is the real cost: while the suspension holds, the cause-attribution layer
has no gate that can fail for being wrong about a cause.

What is unaffected, and why:

- **Section 14.3**, event detection and duration exactness. Both are checks of the parser against
  the source XML, and `src/volve_ops/extraction/integrity.py` runs them on a **second** walk. Second
  and not independent: it shares three names with the extractor, which its own docstring counts, and
  protocol amendment 8 records the same overclaim being made about the section 20.2 walk. 617 qualifying blocks across the labelled sample's 99 documents, both marks
  passed. The scope is narrow on purpose and should not be read as general parser correctness: both
  marks can pass while `state_detail`, `subcategory` or `comment` is wrong, and those are what the
  `echo-statedetail` baseline and the cause layer are built from.
- **Section 14.5 condition 3**, span validity. A span either is a substring of the comment it
  cites or it is not. All 60 attributed labels carry a verbatim span, checked on every read. It
  compares the span against the extractor's own comment field, so a comment attached to the wrong
  block would satisfy it.
- **Both baselines and both mapping tables.** Fixed in section 14.4 before any label existed and
  exempt from amendment, so the opponent in any comparison is honest. What the labels contaminate
  is the target, not the baselines.

Section 17.4 fixes what would restore the suspended marks, before any of it is available: a
reader with drilling-operations experience adjudicates 40 events drawn by the guide's existing
subsample rule, blind to the machine labels and to the baselines, and agreement of at least 80
percent restores them. That threshold is fixed now so it cannot be set later to whatever the
adjudication produces.

## The label file is committed, which is an exception worth naming

This project does not commit raw or processed data; `.gitignore` excludes `/data/` outright and
`docs/data_manifest.md` carries checksums instead. `labels/development_pass1.jsonl` sits outside
that directory and is committed deliberately.

It embeds 60 verbatim spans of drilling-report comments, so it does contain source text. The
alternative is a benchmark whose labels nobody can inspect, which would make every figure in
`docs/labelling_results.md` an assertion. For a label set whose provenance is already its weakest
property, that is not a trade worth making: the labels are published precisely so a reader with the
domain knowledge the labeller lacked can overturn them.

The spans are short quotations from an openly licensed dataset. The Equinor Open Data Licence
permits producing and sharing adapted material, requiring attribution, no sale, and no misleading
presentation; `NOTICE-VOLVE.md` and `DATA_LICENSE.md` carry the attribution. Published prose in
this repository already quotes comments the same way.

What stays excluded is unchanged: the drilling reports, the production data, the extraction store
and every processed artifact. The exception is the label set and nothing else.

## Consequences

The project cannot claim that any approach reads drilling narrative well. It can claim that an
approach reproduces this guide's taxonomy more closely than a fixed lookup table does, which is
narrower and is the only claim that will be made. A reader who wants the stronger claim is told
exactly what is missing and what would supply it.

The deterministic layer is unaffected. Per-well NPT totals by category and duration come from the
structured fields and from section 14.3's two passing marks, and no cause label enters them.

Two numbers are lost. Inter-pass agreement, because re-running a model over the same comments
measures procedural stability rather than a person's consistency with themselves, and reporting
it under the old heading would be a borrowed figure. And an anchoring rate: an earlier plan had
the model recommend a label for the author to accept or override, which would have measured how
far the recommendation moved the human. With no human in the loop there is no override to count.

## What labelling found out about the guide, including one mistake caught in review

Labelling 135 comments surfaced seven recurring shapes the guide's rules did not settle on their own.
They are now written into the guide, dated as post-labelling, and recorded as protocol amendment 3,
because a section added to a pre-registered document after the fact is an amendment to it.

Five only named a rule already present. One changed three labels: a failed test with a quantified
fault symptom, or negatives isolated to one named component while another tests good, now reads as
plainly implying a component failure rather than as a bare unsuccessful outcome.

**One was wrong and has been withdrawn.** The first pass labelled ten events `equipment_maintenance`
or `rig_service` whose whole comment is work on named equipment or a rig operation, reading precedence
rule 3 as licensing that. Independent review pointed out that precedence rule 1 says an activity
description is not a cause and "outranks every one below it", that its own examples are exactly those
shapes, and that all ten spans were the activity description, which the span convention forbids in the
same sentence. All ten are now `not_stated`.

That correction changed published figures: both baselines' macro-F1, both exact-agreement rates, the
number of classes in the macro average, and which baseline leads. It also cost a finding this project
had nearly published, that the two metrics disagreed about which baseline was better. They disagreed
only because the mislabelled events sat in a class one baseline can emit and the other cannot.

What the withdrawal exposed is worth more than what it cost. **Rule 1 makes `equipment_maintenance`
and `rig_service` unreachable**, because any comment that would earn either is an activity
description. Both are absent from the sample as a result, and three of twelve taxonomy classes are
unused. That is a defect in the guide, and fixing it needs a new guide version in its own pushed
commit rather than an edit made while labelling against it.

A narrower defect, left in place for the same reason: rule 2 gates `equipment_failure` on a named
fault, so "Repaired flowline isolation valve" names none and falls through. Under rule 1 it reaches
`not_stated` anyway, so the gate no longer decides anything here, but the wording is still wrong.

One deviation in the labelling pass itself, disclosed because section 14.2 exists to make it
checkable: the pass saw the wellbore identifier alongside the permitted evidence. A wellbore name
carries the era, and era plausibly moves a cause label. The adjudication worksheet withholds it, so an
adjudication is scored against labels made with slightly more context than the adjudicator had.
