# Evaluation protocol

Version: v6
Date: 2026-10-06
Status: pre-registered. Pushed before the work it judges.
Amendments since v0: three, in sections 6 and 14.5 and in the labelling guide, all recorded in
section 13 and all labelled post-inspection.
New in v3: section 17 fixes where the cause labels come from, and suspends the section 14.5
selection gate because they are not expert labels. No threshold is lowered and no baseline moves.
New in v4: section 18 fixes the investigation layer, before any investigation has been run.
New in v5: amendment 4 records every threshold the investigation layer turned out to need, all of
them chosen after v4 was tagged and all labelled post-inspection, and corrects two stop-condition
definitions that the implementation did not match.
New in v6: section 19 fixes the evaluation harness, before it is built. Unlike section 18 it states
its own numbers, which is the lesson amendment 4 recorded.

This file states how the project will be judged, and it is pushed to the public remote
before the runs it judges happen. The published history is the evidence. Pass marks,
feasibility criteria and hold-out definitions appear here first and in code second.
Where this file and an implementation disagree, this file is the specification and the
implementation is wrong.

The protocol is versioned rather than edited in place. Section 13 sets out how it may
change and what a change has to disclose.

## 1. Pre-registration record

Two separate statements, because they rest on different kinds of evidence.

Verifiable from this repository: no data file has been retrieved into it. There is no
`data/` directory, the file tables in `docs/data_manifest.md` are empty, and the history
up to this version contains no code that reads a dataset.

Attested by me, the author: I had not opened, downloaded or viewed any file of the
dataset when this version was written, here or anywhere else. No artifact can prove that
for me, which is why it is stated separately from the paragraph above.

What is known, and was known before writing this, is the dataset's public description:
which classes of measurement a production record of this kind contains, that drilling
reports are distributed as XML alongside narrative documents, and the field's rough
operating era. No values, row counts, well names, column names, date ranges, coverage
figures or distributions have been seen.

The sections below name five things on the strength of that public description alone:
on-stream hours, oil volume, well status, choke setting, and dated drilling,
intervention and completion records. Each is named because a production record of this
kind normally carries it, not because it has been seen here.

Well status, choke setting and dated activity records each have a stated fallback in
sections 6 and 7, so that a missing one degrades the method visibly instead of invalidating
it. On-stream hours and oil volume have none, and cannot: the rate normalisation and the
shortfall are defined in terms of them. If either turns out to be absent, this protocol
cannot be applied as written, and replacing it is an amendment under section 13 rather than
a quiet substitution.

This ordering matters because every threshold here is a free parameter. Chosen after
seeing the data, a threshold stops testing a question and starts ratifying an answer
already preferred. Choosing blind is what allows the criteria below to fail honestly.

The thresholds are therefore judgement calls from domain reasoning, not from this
dataset. Some will be badly sized. The remedy when that happens is an amendment under
section 13, labelled as post-inspection, never a quiet edit.

## 2. What this version fixes

Fixed here, and not deferred:

- both feasibility criteria, drilling plan reconstruction (section 4) and allocation
  reconciliation (section 5)
- the day classification, the rate normalisation guard, and the definitions of
  cumulative shortfall and deferred volume (section 6)
- which days and windows are eligible for evaluation at all, including quarantine
  rules and what makes a window stable (section 7)
- expectation-engine pass marks and the baselines they are measured against
  (sections 3 and 8)
- episode criteria, including every tolerance judgement (section 9)
- the split, the buffer, and the frozen hold-out (section 10)
- leakage rules and the version manifest (sections 11 and 12)

Deferred, with the reason:

- One bound in section 7: the absolute implausibility limit on a daily volume, which
  needs a published field or facility capacity figure. It comes from that published
  figure, not from this dataset at all, which is a stronger guarantee than any
  pre-boundary rule.
- The curated episode set's labelling criteria, which cannot be written without knowing
  what a production record of this field looks like. Guarded in section 9: the labelling
  guide is pushed before any label is made, and labels are made without seeing detector
  output.

Settled in v2, and no longer deferred: the extraction and retrieval pass marks and the split
for those layers, in sections 14 to 16. They are fixed before any extraction is run and before
any label is made, which is what makes them pre-registration rather than description.

Anything else these definitions leave open is, when it is later set, an amendment under
section 13 and carries that label. That clause exists so the deferred list cannot be
extended by discovering a convenient gap in it.

Neither remaining deferred item is drawn from this dataset: one comes from a published capacity
figure, the other from a labelling guide. That is deliberate. Had either been a data statistic,
it would have had to be computed from pre-boundary data only, because a threshold drawn from a
whole-record profile is a threshold choice using hold-out data, which section 10 forbids.

Section 16 does report a whole-record statistic, the proportion of drilling-report events its
split holds out. That figure is a consequence of a rule fixed before it was computed, recorded
so a reader can check the rule was not reverse-engineered, and it sets no threshold. It is not
an exception to the paragraph above; it is a different kind of number.

The contract on the next version is narrow. It may fill only the blanks named above. It
may not change any number fixed in this version. A later version that alters a v0
threshold is an amendment under section 13 and carries that label.

## 3. How pass marks are set

Pass marks are relative to baselines named in advance, not absolute values.

An absolute target chosen without seeing the data is either so loose that passing means
nothing or so tight that failure reflects the dataset rather than the engineering.
Neither tells a reader anything. A requirement to beat a named baseline by a stated
margin is falsifiable, independent of how hard the dataset happens to be, and has a
defined outcome when it fails.

Two baselines, fixed here, exempt from amendment under section 13:

- `naive-median28`, the robust median of normalised rate over the last 28 valid
  producing days (both terms defined in section 6), carried forward over the evaluation
  horizon
- `naive-persistence`, the normalised rate of the most recent valid producing day,
  carried forward over the evaluation horizon

Each baseline also carries an interval, because a point forecast cannot serve as an
expectation for a detector that compares against a band. The interval for both is the
empirical 10th and 90th percentile of normalised rate over the same trailing 28 valid
producing days.

Both are computed under the section 6 and 7 definitions, on the same windows, with the
same exclusions as any candidate model.

Every threshold below states the reasoning that produced it, in the text beside it. A
number with no stated derivation does not belong in this document, because a reader
cannot tell such a number from one chosen because it looked about right.

## 4. Drilling plan reconstruction

The question: can planned drilling durations be reconstructed from auditable source
data, so that a planned-versus-actual view reports something real?

Let `N` be the number of distinct canonical wells with any daily drilling report
coverage. Required wells `W = max(1, min(3, ceil(N / 2)))`. If `N` is zero this
criterion fails outright, with no further checks.

A distinct canonical well counts once. Sidetracks and wellbores of the same well are
one well for `W`, and the canonicalisation in section 6 must resolve well versus
wellbore explicitly.

All five conditions must hold.

1. A planned duration, or a planned depth-versus-days schedule, is present for at least
   one drilled section or operational period. Presence means a named structured field
   in an XML document, or a verbatim quotable text span in a document such as a
   drilling programme, an end-of-well report or a time estimate.

   These do not count: a planned total depth with no time dimension; a rolling
   next-24-hour forecast, which is an operational look-ahead rather than a plan; any
   figure written during or after execution of the period it describes; and a plan
   present only as a chart image, since it cannot be quoted or audited.

2. Condition 1 holds for at least `W` distinct canonical wells.

3. For each qualifying well, planned values cover at least 60 percent of that well's
   drilling-reported days. The denominator is all days with a drilling report for that
   well's wellbores, excluding days whose reported activity is completion or
   intervention rather than drilling. The numerator is drilling-reported days falling
   inside an operational period that has a stated planned duration. Below 60 percent, a
   planned-versus-actual chart is mostly gaps and presenting it would overstate the
   data.

4. The planned value is a stated plan that predates the period it covers. A figure
   back-computed from actuals, or inferred from a later summary of what happened, does
   not count.

5. Planned and actual can be aligned on a common basis, with units and reference point
   determinable from the source. Alignment at section boundaries is acceptable.
   Interpolating a plan to a finer granularity than the source states is not.

Pass: build the planned-versus-actual view.

Fail: the time breakdown carries three categories, non-NPT recorded time, NPT, and other
unclassified time, and the interface says outright that the source material does not support
a planned duration for these wells. Nothing stands in for the missing plan. No estimate,
inference or back-computed figure is presented as a baseline, because a fabricated baseline
would make every comparison against it meaningless while looking authoritative. ADR 0002
records why the first category is not called productive time.

Recorded before looking: failure is the expected outcome, because open datasets rarely
include the drilling programme. The failure path is designed and costs nothing, so a
failure here is a result rather than a setback.

## 5. Allocation reconciliation

The question: does an independent aggregate production series exist that can be
compared honestly against the sum of per-well allocated volumes?

In scope: series inside the dataset, and aggregate figures published by a regulator or
other public body for this field. An external public series is admissible only if it is
recorded in `docs/data_manifest.md` with its source and retrieval date, like any other
input.

All four conditions must hold.

1. An aggregate series exists, for example a field export, a fiscal or sales meter, or
   terminal liftings, and its derivation can be shown to be independent of the per-well
   allocated volumes. A series that cannot be shown to be independent fails this
   condition, rather than being given the benefit of the doubt.
2. Its measurement point and basis are documented or determinable: what is measured,
   where in the process, in what units, at what frequency. An operator-reported
   aggregate with no stated metered-versus-allocated basis fails here, and this is the
   likeliest failure mode for a public regulatory series.
3. It overlaps the per-well record by at least 24 months at a consistent daily or
   monthly frequency.
4. The comparison needs no allocation factor that is itself derived from the per-well
   data. A reconciliation that assumes the thing it reconciles proves nothing.

Pass: a reconciliation capability remains possible, and stays deferred until the
well-investigation and drilling-report capabilities are complete. Depth before breadth.

Fail: document why an allocation reconciliation cannot be reconstructed from this
dataset. The feasibility finding is itself an engineering outcome.

## 6. Day classification, rates, shortfall

Every downstream number depends on which well-days count and how daily volumes become
rates, so both are fixed here rather than in the implementation.

Each well-day is assigned exactly one class, by the first rule that matches:

1. **Missing**, if on-stream hours is absent; or well status is absent on a day where a
   status field exists; or oil volume is absent on a day whose status indicates production,
   or whose source carries no status field at all. Excluded everywhere and flagged. Missing
   is never coerced to zero. Zero means measured zero. Per-row nulls are the normal case in a
   daily production record rather than an edge case, which is why a null status lands here
   instead of being read as "not producing".

   The qualifier on oil volume is what stops an injector being called missing. A water
   injector has no oil volume by nature rather than by omission, and an unqualified test
   would class every one of its days as a gap in the record. Quarantine is still tested
   before non-producing, so a physically impossible injector row, for instance one reporting
   more than 24 on-stream hours, is still caught rather than waved through.
2. **Quarantined**, if the day fails any physical check in section 7. Excluded from
   fitting and from evaluation, counted, and the quarantined fraction per well is
   reported next to every result that depends on it.
3. **Non-producing**, if well status indicates anything other than production. Tested
   before the hour-based classes, so that a well shut in or converted to injection is
   never read as downtime on a producing well. Without this ordering, a permanently shut
   well would accrue deferred volume for the rest of the record.
4. **Downtime**, if on-stream hours are exactly zero.
5. **Partial**, if on-stream hours are above zero and below 6.0.
6. **Valid producing day**, otherwise. Equivalently: on-stream hours at least 6.0, status
   production, oil volume present, no physical check failed.

A valid producing day may have an oil volume of zero. A well that flowed a full day and
made no oil must not be removed by a positivity test, because that is one shape a severe
problem takes in the data. The honest caveat is that it is also the shape of a recording
gap, and in an allocated daily record the recording gap is the likelier of the two. So
section 7 quarantines the uncorroborated case: zero oil with nonzero hours and no gas and
no water reported. What survives that check, a full producing day with no oil but
measurable gas or water, is a real underperformance signal.

Normalised rate, on valid producing days:

```
q_24h = oil_volume / on_stream_hours * 24
```

`q_24h` is expressed in standard cubic metres per day (Sm3/d). Sm3 is the canonical
volume unit for every liquid and gas quantity in this project, and conversion to it
happens at ingest, before this step. Any source reported in another unit is converted
once, at the boundary, and the original unit is recorded in the data manifest.

The 6.0 hour floor exists because the multiplier grows without bound as hours fall. At
four hours the factor is six, and it scales measurement error, allocation error and
within-day ramp behaviour by that same six. A rate extrapolated from a short producing
window is not comparable to a full-day rate, and treating them as interchangeable is
how a detector invents shortfalls. Six hours is one quarter of a day, giving a
multiplier of at most four. It is a judgement made blind, revisable only through a
declared amendment.

If the dataset has no well-status field, class 3 disappears and class 6 drops its status
test, so classification rests on hours and volume alone. The absence is then disclosed wherever status-dependent
results are reported, because without it a day on test or on injection cannot be
distinguished from a producing day.

Expected volume, for every day whose class is downtime, partial or valid producing:

```
V_expected = q_expected * min(on_stream_hours, 24) / 24
```

This makes downtime days contribute nothing and partial days contribute in proportion,
with no discontinuity at the 6.0 hour boundary.

Missing, quarantined and non-producing days get no expected volume and contribute zero
to both sums below. Non-producing days are excluded deliberately: a well that is not in
production service has no production expectation, and booking shortfall or deferment
against it would attribute a loss to a well nobody expected to produce.

Two quantities follow, and they are reported separately because they mean different
things:

- **Cumulative rate shortfall**, the sum of `V_expected - V_actual` over the window.
  This is production lost while the well was flowing. It is the quantity the episode
  threshold in section 9 applies to.
- **Deferred volume from downtime**, the sum of
  `q_expected * (24 - min(on_stream_hours, 24)) / 24` over the window. This is volume not
  produced because the well was not flowing. It is an estimate, labelled as such, and it
  is never added to rate shortfall to make a single headline number.

The two are complementary by construction: for any day in scope,
`V_expected + deferred = q_expected`, so nothing is double counted and nothing falls
between them.

Separating them keeps uptime loss available as an explanation for an episode without
letting it manufacture one. A well that was shut in for half a month has a large deferred
volume and may have no rate shortfall at all, and an investigation should say exactly
that.

One asymmetry follows from the 6.0 hour floor and is load-bearing, so it is stated rather
than left to be discovered. A partial day does not count toward the duration conditions in
section 9, which are counted in valid producing days, but it does contribute to the
cumulative rate shortfall summed over the same window. That is deliberate: the volume
comparison needs no extrapolation, so it is trustworthy on a short day even though the
rate is not. Partial days can therefore help an episode clear its volume threshold while
never helping it clear its duration threshold.

Quarantined and missing days inside an episode window contribute zero to both sums. They
neither break a run of consecutive valid producing days nor count toward it: a gap is
treated as an absence of evidence, not as evidence either way. The combined quarantined
and missing fraction inside each episode window is reported beside that episode, and an
episode whose window is more than one third quarantined or missing is flagged as
poorly evidenced rather than reported as detected.

Well-name canonicalisation must be total. Every name in every source resolves to one
canonical well entity, with wellbore and sidetrack relationships explicit, or is
quarantined. A silently unmatched name is a failure, not a warning.

## 7. Eligibility: quarantine and window definitions

These definitions decide which data an evaluation sees. If they were left to the
implementation, a builder could quarantine the days that embarrass a model and call every
inconvenient window abnormal. All of them are therefore fixed here, all are independent of
any model output, and all decisions under them are made before any model is fit.

The episode window is deliberately not defined here. It is the detector's own output span
and necessarily depends on the expectation, so it belongs in section 9. Nothing in this
section may reference a model.

A day is **quarantined** if any of these holds:

- on-stream hours below zero or above 24
- any reported volume below zero
- a nonzero oil volume on a day with zero on-stream hours
- zero oil volume on a day whose status is production, with nonzero on-stream hours and no
  gas and no water reported, which separates a recording gap from a genuine no-oil
  producing day. The status qualifier matters: without it an injection day with no
  produced fluids would be quarantined rather than classed as non-producing, inflating the
  quarantine fraction of every injector. If the source carries no gas or water columns this
  check cannot run; it is then disabled and the absence is disclosed wherever affected
  results are reported.
- duplicate rows for the same well and date that disagree on any of on-stream hours, oil
  volume, gas volume, water volume, well status or choke setting. Disagreement in a
  column this project does not use is not a reason to discard a usable day. Duplicate
  rows that agree on all of those are collapsed to one, which is what makes the
  one-class-per-well-day rule above well defined.
- a daily volume above an absolute implausibility bound

The implausibility bound is the one deferred item here. It is set from a published field
or facility capacity figure, stated in the next protocol version, and it is an absolute
bound. It may not be derived from model residuals, from the detector, or from any
quantile of the data that a model has been fit to.

No quarantine rule may reference a residual, a prediction, or a detector output, in
this version or any later one.

A **stable reference window** is one where all of these hold:

- no change in well status inside the window
- choke setting stays within plus or minus 10 percent of its median over the window,
  measured relatively, in whatever unit the source records the choke in. If the source
  carries no choke record, this test is dropped and the window rests on status and
  activity records alone, with the absence disclosed wherever window-dependent results
  are reported.
- no drilling report, intervention record or completion activity dated inside the window.
  If the source carries no dated activity records at all, this test is dropped, the window
  rests on status and choke alone, and the absence is disclosed wherever window-dependent
  results are reported.
- at least 20 valid producing days
- no quarantined days

Where several stable reference windows qualify, the one used is **the most recent
qualifying window ending before the first day of the candidate episode, taken at maximal
extent**. Without this rule the choice among qualifying windows would be free, and since
the window sets `q_ref` in section 9, a free choice there would silently set the episode
threshold.

A **normal window**, used for the false-episode rate, is a stable reference window that
does not overlap any episode in the curated episode set. Where curated labels are used,
they are made without seeing detector output.

Both window definitions here rest only on operational facts. Neither may be narrowed by
reference to how a model performed inside the window.

## 8. Expectation engine pass marks

The expectation engine is evaluated on its own, before any agent reasoning is built on
it, because a bad expectation manufactures investigations that have nothing to
investigate.

WAPE is `sum(|actual - predicted|) / sum(|actual|)` over the evaluated days.

Evaluation mimics how the expectation is actually used: fitted on data up to the end of
a stable reference window, then carried forward over a horizon of `H` valid producing
days without refitting. `H` is evaluated at 7, 14 and 28. The conditions below must hold
at all three horizons, because a model with one-day skill and no multi-week skill is
useless to a detector that holds an expectation across a sustained episode.

A candidate model is selected only if all three conditions hold.

1. Pooled WAPE at least 10 percent lower in relative terms than the better of
   `naive-median28` and `naive-persistence` on the same windows and horizons. Relative
   means `(WAPE_baseline - WAPE_candidate) / WAPE_baseline >= 0.10`. Pooling is over
   all evaluated well-days. Per-well WAPE is reported alongside, with a small-sample
   caveat, and is not itself a pass condition.

2. Lower-tail calibration. The detector only ever compares against the lower edge of the
   band, so that edge is what has to be calibrated; a two-sided coverage figure can hide a
   badly placed band entirely. For each well with at least 150 evaluated valid producing
   days, the 95 percent Clopper-Pearson interval for the fraction of days falling below the
   lower edge of the nominal 80 percent interval must lie entirely within 0.05 to 0.20.

   The bounds come from the detector's behaviour: false-episode load scales roughly with the
   lower-tail rate, so twice nominal is the ceiling, and at half nominal the band is too wide
   to detect anything.

   The 150-day gate is arithmetic, not a round number. Interval containment inside bounds
   that narrow is unachievable at small counts: at 60 evaluated days no observed count
   produces a containable interval at all, so a 60-day gate would fail every such well
   regardless of how well calibrated it was. At 82 days exactly one count qualifies. At 150
   the admissible band is 0.093 to 0.133, which is wide enough that a well passes or fails on
   its calibration rather than on its sample size. The gate is set where the criterion starts
   measuring the thing it is meant to measure.

   Containment is used rather than a point test against the nominal 0.10 because a point test
   has the wrong behaviour at both ends: at 60 days it does not reject even a rate of 0.13,
   and by several hundred days it rejects 0.13 even though the reasoning above calls that
   acceptable. Containment instead fails a well when its rate is demonstrably outside the
   tolerable range, and also when there is too little data to tell either way, which is the
   correct treatment of ignorance.

   The caveat: Clopper-Pearson assumes independent trials, and lower-tail exceedances inside
   a carried-forward horizon are serially correlated, so the effective sample size is below
   the nominal count and the interval comes out narrower than it should be. Where the count
   allows it is widened by a block bootstrap over blocks of consecutive calendar days, which
   preserves the dependence structure; resampling only the exceedance runs would not be a
   valid unit for estimating the rate. The method actually used is recorded with the result.

   Wells below 150 evaluated days are report-only. Two-sided coverage of the 80 percent
   interval is reported alongside, without a pass mark attached.

3. Mean residual within plus or minus 5 percent of that well's mean observed `q_24h`,
   for wells with at least 60 evaluated valid producing days. The mean, not the median,
   because cumulative shortfall is a sum, and a skewed residual distribution can sit at
   median zero while accumulating a standing apparent shortfall. The median is reported
   too. Drift is tested per evaluated stable reference window and horizon: each window is
   split at its midpoint in valid producing days and the same bound is required in both
   halves. That is checkable, unlike an eyeball test. The bound is tight relative to daily
   noise on a short window, so a genuinely unbiased model can still fail it on some well;
   the aggregation rule below is what decides the outcome in that case.

Conditions 2 and 3 are per-well, so the rule for combining them across wells is fixed here
rather than left to whoever runs the comparison. Both must hold for every well reaching the
qualifying count: 150 evaluated valid producing days for condition 2, 60 for condition 3,
which needs no interval and so needs no larger gate.

If fewer than half the field's oil producers reach the condition 2 gate, that condition is
evaluated pooled across all evaluated well-days instead, under the same containment bounds,
and the result is labelled as pooled. Pooling is the weaker test, because a pooled rate can
sit inside the bounds while one well runs at 0.03 and another at 0.25, so the per-well rates
are reported beside it and the limitation is stated wherever the result appears. A pooled
check that is honest about what it hides beats reporting a criterion as not evaluable when
the data could support a weaker version of it.

If fewer than half reach the condition 3 gate, condition 3 is reported as not evaluable with
the qualifying count stated, and selection rests on the remaining conditions with that
limitation disclosed.

Each condition's outcome is reported separately. If a candidate fails, the report names
which condition failed and by how much, because failing calibration and failing point
accuracy call for different work.

If no candidate passes, `naive-median28` with its section 3 interval becomes the
expectation model, and that outcome is reported as the headline result. It is
`naive-median28` specifically, not the better WAPE performer:
`naive-persistence` cannot serve as an expectation at all, because after one day of
reduced rate the reduced rate becomes the expectation, and sustained underperformance
becomes undetectable by construction. Persistence stays in as a WAPE comparator only.

Reported without pass marks: MAE, interval width, residual distribution by well and by
operating regime, behaviour on windows adjacent to known operational changes, and the
full candidate comparison with the selection rule applied.

## 9. Episode criteria

**Trigger.** A candidate episode is triggered by a run of at least 7 consecutive valid
producing days whose observed rate is below the lower edge of the expectation interval.
Consecutive counts valid producing days, not calendar days, so downtime cannot trigger one
by itself.

**Window.** The episode window opens on the first day of that run. It closes on the last
valid producing day below the lower edge before the first occurrence of three consecutive
valid producing days at or above it. A single good day does not end an episode, because
production that recovers for a day and drops again is one problem, not two; three is the
smallest run that distinguishes a recovery from noise. If no such recovery occurs before
the record ends, or before a status change takes the well permanently out of production
service, the window closes at that point and the episode is reported as open-ended.

Because the window tolerates short recoveries, it can and usually will contain more valid
producing days than the triggering run, and some of them will sit above the lower edge. The
window is the extent of the episode; the run is only what starts it.

Onset is the window's first day, offset its last. Those are what the timing-error metric
below measures.

An episode is opened only when all four hold:

1. The trigger condition above is met.
2. The window is formed by the rule above.
3. The window contains at least 10 valid producing days, which a 7-day trigger run alone
   does not satisfy, so a short dip that never develops is not opened as an episode.
4. Cumulative rate shortfall over the episode window, as defined in section 6, is at least
   `0.15 * q_ref * n_vpd`, where `q_ref` is the median `q_24h` of the stable reference
   window the expectation was fitted on, selected by the rule in section 7, and `n_vpd` is
   the count of valid producing days in the window. `q_ref` is a rate and `n_vpd` a count of
   days, so the product is a volume and compares against a volume.

The constant 0.15 is fixed here. The reasoning: a shortfall under roughly 15 percent of what
the reference window would have produced over the same number of producing days is within
the range daily allocation error produces on its own, and opening an investigation into it
would waste a reviewer's time.

The threshold scales with `n_vpd` rather than sitting at a fixed floor. A fixed floor would
leave long windows decided by the trigger and duration conditions alone, which is backwards:
allocation drift accumulates with length, so long windows are exactly where a slow bias is
most likely to masquerade as an episode.

`q_ref` is a run-time statistic of whichever reference window the expectation was fitted
on, not a constant to be filled in later. It is not in the deferred list in section 2,
because section 7 fully determines which window is used and therefore what `q_ref` is.

A calendar sweep is not the detector. Quarters and months have no operational meaning
here and are not used as a unit of detection.

Metrics: episode precision and recall against a curated episode set, onset and offset
timing error in valid producing days measured against the window bounds defined in section
7, cumulative shortfall error, and false episodes per well-year on normal windows.

The false-episode rate must be at most 2 per well-year. That is a permissive bar, chosen
deliberately: on a small field over a decade it still allows tens of false candidates
across the record, and the cost of a false candidate here is a reviewer's time rather than
a wrong operational decision, since nothing downstream acts without human review. If the
selected expectation and detector exceed it, the detector is reported as not meeting its
pass mark, and its output is presented as candidate windows for review rather than as
detected episodes. The pass mark has a stated consequence so that it is falsifiable in the
same sense as everything else here.

The curated episode set determines both parts of that metric, so its construction is
guarded rather than left open. The labelling guide is written and pushed before any label
is made. Labels are made without seeing detector output. The guide states what counts as an
episode independently of the detector's own criteria, so the two cannot be tuned toward
each other, and the number of labels plus the labeller count is reported with any figure
derived from them.

If the curated set is too small or too ambiguous to support a meaningful precision and
recall figure, that limitation is reported as such, and deterministic invariants plus
curated cases are used instead. A manufactured precision figure from eight labelled
episodes is worse than no figure.

## 10. Split, buffer, hold-out

Scope: this section governs the production-episode layer. The drilling-report
extraction labels and the retrieval gold set have different units, and for drilling
reports a production calendar boundary would be close to meaningless. Their splits are
fixed in the protocol version pushed before those layers' first scored run, under the
same rules as this one.

The production record runs from the first to the last valid producing day across oil
producers. Injection-only wells do not define its bounds.

The split is temporal. The hold-out is the most recent 25 percent of that record by
calendar time, as one boundary common to all wells.

The boundary is computed and frozen as soon as the record's first and last dates are
known, at the end of data profiling, not later. From that moment every fit, backtest,
label, curated case, prompt iteration and threshold choice uses pre-boundary data only.
Freezing it later would mean the early development work had already been done on data
that includes the hold-out.

Data profiling itself runs over the whole record, including the hold-out period:
coverage, units, missingness and parseability cannot be established on a fraction of
the data. That exposure is accepted and disclosed here. It is structural exposure, not
result exposure. No model is fit, no threshold is tuned and no case is curated on
post-boundary data.

A buffer of 90 calendar days separates development from hold-out. It is carved out of the
development side: development data ends 90 days before the boundary, and the hold-out keeps
its full 25 percent. No model may be fitted or selected on data dated inside the buffer.

The buffer exists to stop model selection being driven by targets immediately adjacent to
the boundary, and to keep residual autocorrelation from carrying information across it. A
trailing feature reading development data is not itself leakage, and the buffer is not
claimed to prevent that.

It is an exclusion band and nothing more. In particular it places no limit on how much
history a model may use. A trailing window reaching far back from a point before the buffer
carries no boundary information, so capping window length would buy nothing, while it would
rule out the decline-curve models that are the standard expectation for a producing well.
Those fit a sustained post-transient decline, which generally needs months of history rather
than the 90 days a cap would have permitted, and excluding them through a side effect of a
leakage rule would have been a real commitment made by accident.

Window lengths elsewhere in this document are counted in valid producing days, the unit the
method operates on. The buffer is the exception and is stated in calendar days, because a
calendar gap is what separates two date ranges.

Wells with fewer than 150 valid producing days before the buffer are excluded from hold-out
scoring and reported separately as cold-start cases. In a field developed in stages, a late
well can have most of its life after the boundary, leaving nothing to fit on.

If fewer than half the field's oil producers survive that rule, the hold-out is reported as
too thin to support a generalisation claim, with the surviving count stated, and its results
are presented as a single-period check rather than as evidence of generalisation.

Acknowledged now, so it is not discovered and amended later: the final quarter of a
field's life is its low-rate, high-downtime tail, and is not representative of the
development period. Hold-out error is expected to be worse than development error for
that reason alone, and the comparison is reported with this caveat attached rather than
explained away afterwards.

Hold-out rules:

- no model selection, threshold tuning, prompt iteration or label revision uses
  hold-out data
- hold-out results are not computed, viewed or partially inspected before the final
  scoring
- it is scored once. If a defect forces a second scoring, both are reported, with the
  defect and the date, and the first is not discarded.

## 11. Leakage rules

Operator corrections are versioned artifacts rather than accumulated memory. A correction
that originates in a hold-out case is barred from the correction store that any hold-out
scoring run reads, because a system corrected using the answers is no longer being tested on
them. Such a correction is admissible only to a system version declared after that scoring.

Every evaluation run records `correction_store_version`. An automated test proves that a
hold-out-derived correction cannot reach the prompt or few-shot context of a hold-out
scoring run. That test runs in the cheap CI suite, not as a manual check, because a
manual check is not a guarantee.

## 12. Version manifest

Every scored run records and freezes:

```
dataset_version
label_set_version
prompt_version
model_role_mapping_version
retrieval_index_version
correction_store_version
parser_version
extractor_version
tool_service_version
commit_sha
```

A headline result that cannot be traced to a complete manifest is not reported as a
result.

## 13. Amendments

This document is versioned and never silently edited. Each version is a tagged commit of
this file, tagged `prereg-v<N>`, so that any change between versions is a reviewable diff
against a fixed point rather than a claim about what used to be written here.

An amendment states the reason, the previous value, the new value, and whether the
change was made before or after the data it affects was inspected. A post-inspection
amendment carries that label wherever the affected result is reported. The label is the
point: a reader can then discount the change instead of taking it on trust.

The two baselines in section 3 are exempt. They cannot be amended, because a pass mark
defined relative to a baseline means nothing if the baseline can move.

Tightening a pass mark after seeing a result that failed it is not an amendment. It is the
failure mode this document exists to prevent.

### Amendment 4, v4 to v5: the investigation layer's thresholds, and two stop conditions

Date: 2026-10-06. Made **after** the investigation layer was implemented and run on development
episodes, and labelled as such wherever a dependent result is reported. Prompted by independent
review, which pointed out that section 18 as tagged contained no numeric threshold at all while every
decision the layer makes turns on one.

**The thresholds, all chosen after the v4 tag.** They are recorded here so a reader can see which
numbers are pre-registered and which are not, rather than having to read the source to find out.

| constant | value | what it decides |
|---|---|---|
| `STRONG_SHIFT` | 1.0 sd | a channel movement that can support a hypothesis |
| `WEAK_SHIFT` | 0.5 sd | a movement that can make one plausible |
| `MIN_RELATIVE_SHIFT` | 0.10 | the movement must also be this large in its own units |
| `WATER_CUT_RISE` | 0.05 | a water-cut rise that supports the water hypothesis |
| `MIN_DAYS_FOR_A_SUMMARY` | 3 | readings a channel needs before anything is concluded from it |
| `EVIDENCE_WINDOW_DAYS` | 45 | how far either side of an episode a report may be dated |
| baseline `MIN_STANDARDISED_SHIFT` | 1.0 sd | when `strongest-deviation` names a channel |
| baseline window | 60 days | the well's own comparison period |

Two of these need more than a row. **`MIN_RELATIVE_SHIFT` was added in response to an observed
result**, which is the most serious thing on this page: a test showed that a well whose choke had sat
at 50, 51, 52 for two months has a baseline spread near 0.8, so a drop to 50 is a 1.2-sigma movement
and a 2 percent change, and the layer was ready to call that the supported explanation for a lost
third of the rate. The fix is defensible on physical grounds and it is still a threshold chosen after
seeing output, and it moves the verdict distribution and the baseline-agreement figure. Both are
reported as post-inspection. **`EVIDENCE_WINDOW_DAYS` is outcome-determining**: at 45 days, 12 of 14
episodes have no drilling report in range; at 180 days, 10 of 14 do. Any claim about document
availability has to name the window, and ADR 0008 does.

**Section 18.3, conditions 1 and 2, corrected to what the implementation does.** Condition 1 said
`evidence_threshold_met` means "every open hypothesis is supported or contradicted". The layer sets it
when no hypothesis remains **plausible**, treating a `weak` one as settled. That is the correct
reading and the original wording was wrong: a weak hypothesis is one whose channel moved slightly,
and no amount of narrative turns a slight movement into support or a contradiction, so "open" can only
mean a hypothesis more evidence could still move. Condition 2, `evidence_exhausted`, likewise now
means a pass added nothing new **or** the pass budget ran out while something remained plausible.

Condition 3 is also narrowed to what the code does: it fires when no hypothesis is supported and an
unresolved one needs a channel this well and period do not have, rather than on "the leading
hypothesis", which does not exist when nothing is supported.

Nothing here loosens a pass mark. Section 18.7's five gates are untouched, section 18.8's deferral is
untouched, and both baselines named in sections 3 and 14.4 are untouched.

### Amendment 3, v2 to v3: a section added to the labelling guide after labelling

Date: 2026-10-06. Made **after** the development sample was labelled, and labelled as such wherever
a dependent result is reported.

`docs/labelling_guide.md` gained a section, "Conventions the first pass had to settle", recording
seven recurring shapes the guide's rules did not settle on their own. The guide is load-bearing for
sections 14.3 and 14.5, so a section added to it after labelling is an amendment to a pre-registered
document and is recorded here rather than as a footnote.

Five of the seven name a rule already in the guide and changed no label. Two did more:

- Convention 4 moved **3 events** from `not_stated` into `equipment_failure`, by reading a failed
  test with a quantified fault symptom, or negatives isolated to one named component, as plainly
  implying a leak. The narrowest reading of the guide would have left them `not_stated`.
- Convention 7 moved **10 events** into `equipment_maintenance` and `rig_service`, and has been
  **withdrawn**. It read precedence rule 3 as licensing those classes for a comment that only
  describes work on named equipment. Precedence rule 1 says an activity description is not a cause
  and "outranks every one below it", and its own examples are those shapes. All 10 are now
  `not_stated`.

The withdrawal was prompted by independent review, before any approach was scored, and it changed
published figures: both baselines' macro-F1, both exact-agreement rates, the number of classes in
the macro average, and which baseline is the better one. The earlier figures are not preserved as an
alternative reading, because they rested on a resolution the guide's top-ranked rule forbids.

What the withdrawal exposed, and what section 14.4's exemption does not permit fixing here: rule 1
makes `equipment_maintenance` and `rig_service` **unreachable**, since any comment that would earn
either is an activity description. Both are absent from the labelled sample as a result. That is a
defect in the guide. Fixing it needs a new guide version in its own pushed commit, and is not done
mid-labelling.

### Amendment 2, v2 to v3

Date: 2026-10-06. Made **after** the drilling reports were inspected and after the development
sample was labelled, and labelled as such wherever a dependent result is reported.

Section 14.5, conditions 1 and 2. Previously an approach was selected only if its macro-F1 beat
the better baseline by at least 20 percent relatively and the margin's bootstrap interval
excluded zero. Both now stand as reported diagnostics and neither selects anything. Section 17
is the new section that records why and what would reverse it.

Reason: the labels are produced by a language model applying `docs/labelling_guide.md`, not by a
reader with drilling-operations experience. Scoring a model's cause attribution against labels
made by a model measures agreement on a shared convention. A margin over the two fixed baselines
earned that way is not evidence about causes in the well.

This is not a pass mark being tightened or loosened after a result. Nothing had been scored
against these labels when the amendment was written, and the amendment removes a claim the
project could have made rather than preserving one. The direction is the test: a protocol edited
to flatter a result moves a threshold toward the result, and this one withdraws the threshold
that a passing result would have been reported against.

What does not change: both baselines and both mapping tables, which section 14.4 exempts from
amendment; the macro-averaging rule and its five-instance floor; conditions 3 and 4; every
section 14.3 pass mark; and the section 16 split.

### Amendment 1, v0 to v1

Date: 2026-10-04. Made **after** the production data was inspected, and labelled as such
wherever a result that depends on it is reported.

Section 6, rule 1. Previously a day was missing if on-stream hours or oil volume was absent,
or if well status was absent where a status field exists. Now the oil-volume test applies only
to a day whose status indicates production, or whose source carries no status field.

Reason: applying the test unconditionally classed every water-injector day as missing, because
an injector reports no oil volume. In the Volve production data that is 6,473 of 15,634 rows.
What changes is the missing fraction this protocol requires to be reported beside every
dependent result: it falls from 41.4 percent of the record to 1.8 percent, because those rows
were injectors behaving normally rather than gaps.

Measured effect of the change, classifying all 15,634 rows under both wordings: 6,181 rows move
from missing to non-producing and 7 move from missing to quarantined, the latter being injector
rows that now reach the physical checks instead of being short-circuited. No row enters or
leaves valid producing, downtime or partial, which are the only three classes that carry an
expectation. Every quantity built on them is therefore untouched in both directions: normalised
rate, expected volume, deferred volume, cumulative shortfall, WAPE, calibration, and the
section 9 volume criterion.

Two routes by which it could in principle have mattered, checked rather than assumed. Section 7
disqualifies a stable reference window containing any quarantined day, while a missing day does
not disqualify one, so the 7 newly quarantined rows could have changed which window is selected
and therefore `q_ref` and the section 9 threshold. They do not: all 7 are injection days on
15/9-F-4, which never produces, and on 15/9-F-5 between 2008 and 2014, outside its producing
span of 21 April to 26 August 2016. Second, section 6 flags an episode whose window is more than
one third quarantined or missing as poorly evidenced, and lowering the missing count lowers that
fraction. No producing well's episode window can contain those rows, for the same reason.

No threshold moved. No pass mark moved. The change was not prompted by any result failing a
criterion, and the detector had not been run when it was made. A reader who wants to check this
rather than take it on trust can reclassify under both wordings; the counts above are what that
produces.

## 14. Drilling-report extraction

What the reports contain was established during data profiling and is recorded in
`docs/data_profile.md`: 1,759 WITSML drill reports carrying 23,447 activity blocks, each with
start and end timestamps, a two-level activity code, an ok-or-fail state, a detail state, and a
free-text comment. What is not known, and what these pass marks judge, is how well anything
extracts from them.

### 14.1 What counts as a non-productive event

A block is non-productive if its activity code begins `interruption`, **or** its state is
`fail`. Both, because the two do not coincide: 3,577 blocks carry an interruption head, 480
carry a fail state, and 96 of those fail-state blocks sit under a different head, mostly
`drilling -- casing` and `drilling -- drill`. A failed casing run is lost time whatever it is
filed under, and the union is 3,673 blocks.

This restates ADR 0005, which named both the interruption head and the failure states. An
earlier draft of this section used the interruption head alone, which would have made counting
any of those 96 blocks a parser defect.

### 14.2 The division of labour, and why it is not negotiable

Non-productive time is identified **deterministically** by the rule above. Duration is the
difference between the block's timestamps. The subcategory is the code's second level. None of
that goes near a model, because none of it needs judgement, and a model asked to classify what
is already classified can only introduce error.

The model is asked one question the structured fields cannot answer: given an event the source
has already categorised and timed, what does the narrative say caused it. Its output is a cause
attribution and a verbatim span of the comment supporting it.

The model is given exactly what the labeller is given, and no more: the comment, the activity
code, the state and detail state, and the timestamps. Pinning this matters because two of the
three baselines below are built from those same structured fields, and a model with access to
material the labeller lacked would be scored against labels made in ignorance of it.

This also fixes what the metrics mean. Category accuracy against the labelled sample would measure the
operator's coding from 2008, not this system's extraction, and reporting it as an extraction
score would be a borrowed number. It is reported as a data-quality statistic instead.

### 14.3 Deterministic layer: pass marks

Measured against the labelled sample described in `docs/labelling_guide.md`. These two pass
marks are unaffected by section 17: both are checks of the parser against the source XML, and
who assigned the cause does not enter either one.

1. **Event detection is exact.** Every block meeting the 14.1 rule in the labelled sample
   becomes exactly one event, and no block failing it does. The pass mark is 100 percent
   agreement, because disagreement is a parser defect rather than a difficulty.
2. **Duration is exact.** Computed duration equals the labeller's reading of the block's own
   timestamps to within one minute. The same reasoning: this is arithmetic.

**What passing these does not establish**, because the pass marks are narrow by design and a reader
could take them for a general parser-correctness claim. They cover which blocks became events and
how long each lasted. They do not check any other extracted field. `qualifying_blocks ==
events_checked` can hold while `state_detail`, `subcategory`, `comment`, `well`, `wellbore` or
`report_date` is wrong, and `state_detail` and `comment` are what the `echo-statedetail` baseline and
the whole cause layer are built from. In particular a comment correctly extracted but associated with
the wrong block would satisfy both marks and would also satisfy condition 3's span check, which
compares a cited span against the extractor's own comment field rather than against the XML.

A failure of either is reported as a parser incident and blocks the layer, rather than being
absorbed into an aggregate score that a strong model could hide.

### 14.4 Cause attribution: the baselines

Two baselines, fixed here and exempt from amendment on the same reasoning as section 3. Both
read nothing. Both are built from structured fields the model also sees, so neither is a straw
opponent, and a system that reads the comment must be shown to add something beyond restating
a label it was handed.

**`echo-subcategory`** maps the activity subcategory onto a cause, by this fixed table:

| subcategory | cause | | subcategory | cause |
|---|---|---|---|---|
| `repair` | `equipment_failure` | | `wait` | `not_stated` |
| `maintain` | `equipment_maintenance` | | `other` | `not_stated` |
| `waiting on weather` | `waiting_on_weather` | | `sidetrack` | `hole_problem` |
| `fish` | `hole_problem` | | `rig up/down` | `rig_service` |
| `lost circulation` | `hole_problem` | | `well control` | `well_control` |

**`echo-statedetail`** maps the detail state onto a cause, by this fixed table:

| detail state | cause | | detail state | cause |
|---|---|---|---|---|
| `equipment failure` | `equipment_failure` | | `circulation loss` | `hole_problem` |
| `stuck equipment` | `hole_problem` | | `mud loss` | `hole_problem` |
| `operation failed` | `not_stated` | | `success` | `not_stated` |

Naming both matters. `stateDetailActivity` marks 1,535 interruption blocks `equipment failure`
outright, which is a strong free signal, and fixing only the weaker baseline while the exemption
locks it in would have left the easier opponent standing. Where a block has neither field, the
baseline emits `not_stated`.

Both tables are part of the baseline definition and are exempt from amendment with it. A
mapping supplied after seeing results is a baseline chosen after seeing results.

### 14.5 Cause attribution: pass marks

**Conditions 1 and 2 are suspended as selection gates by section 17**, which records that the
labels are model-produced rather than expert-assigned. They are computed and reported as
diagnostics. Conditions 3 and 4 still gate, because neither depends on the cause labels being
right: condition 3 checks a span against the text it cites, and condition 4 checks an approach
against itself. Section 17 states what would restore conditions 1 and 2.

The wording below is the wording fixed in v2 and is left intact, so that the diff showing what
was suspended is readable against it.

An approach is selected only if all four hold.

1. **Macro-F1 at least 20 percent higher, relatively, than the better of the two baselines**,
   on the labelled development sample.

2. **That margin survives resampling.** The 95 percent bootstrap interval over labelled events,
   for the difference between the approach and the better baseline, excludes zero. Without this
   the first condition is not a bar: a macro average over eleven classes at a sample of 120 to
   150 events moves by several points when one event in a rare class changes, which is larger
   than the margin being tested.

3. **Evidence-span validity of 100 percent.** Every span must be a verbatim substring of the
   comment it cites, in the document version cited. A hard gate, not a score: a cited span that
   is not in the source is a fabricated citation, and one is too many.

4. **Abstention is available, used, and earns its place.** The approach must be able to return
   no cause. On the labelled sample it must attribute a cause on at least 60 percent of events
   whose label is not `not_stated`, and its precision on the events where it does attribute must
   exceed, by at least 10 percentage points, the precision of the same approach with
   `not_stated` struck from its permitted outputs. The coverage floor is what stops a system
   passing by abstaining on everything except its single most confident event; the margin is
   what stops it passing by a hundredth of a point.

**How the macro average is taken**, fixed here because it changes the number more than the
margin does. Only cause classes with at least five true instances in the labelled sample enter
the average. Classes below that are reported individually with their counts and excluded, and
the number of classes entering the average is reported with every figure. A class absent from
the sample is not scored zero: scoring an unobserved class as a failure measures the sampling,
not the system.

If no approach passes, the deterministic layer ships without cause attribution. Per-well NPT
totals by category and duration are still reportable from the structured fields alone, and that
is an honest product rather than a degraded one.

### 14.6 Reported without a pass mark

Needs-review precision and recall, the labelled sample's own category distribution, the fraction
of comments too short to support any attribution, the distribution of extraction confidence
against correctness, and the rate at which the source's own coding disagrees with the comment.

That last one is a judgement: the labelling guide states the criterion, and applying it needs a
reading of the comment. It is therefore reported beside a **mechanical companion that needs none**:
the fraction of labelled events on which `echo-subcategory` names a cause that is not the label. The
companion is not a better measure of the source's coding, since it is confounded with the labels
being wrong, but it cannot be applied inconsistently, and the first pass applied the judgement
version inconsistently.

Inter-pass label agreement was in this list in v2 and is withdrawn by section 17. It was there to
estimate how consistent one person is with themselves, which is the ceiling on what agreement
with a system can mean. Re-running a model over the same comments does not estimate that, and
reporting the number it produces under the old heading would be a borrowed figure.

## 15. Retrieval

Retrieval covers narrative text only: drilling-report comments and the per-well engineering
documents. Structured data is queried through typed tools and is never embedded, because vector
similarity over numeric tables retrieves the wrong well and the wrong month and gives no way to
tell that it has.

Retrieval failures are recorded separately from reasoning failures. A conclusion that was wrong
because the evidence was never retrieved is a different defect from one that was wrong with the
evidence in hand, and an aggregate that merges them points at neither.

The baseline is fixed here and exempt from amendment:

- `bm25-only`, lexical retrieval with no embedding component, over the same chunks with the same
  metadata filters.

**The pass marks are deferred, and named rather than implied.** Retrieval is scored against a
gold evidence set: for each curated episode, the documents and spans that bear on it. That set
cannot be built yet, because the curated episode set it is evidence *for* is itself deferred by
section 9. Fixing a recall threshold against a set whose construction is unknown would be a
number with nothing behind it.

What is fixed now: the baseline above, the narrative-only scope, and the separation of retrieval
from reasoning failures. What the next protocol version must fix, pushed before any retrieval is
scored: how queries are sampled, the relevance scale, who judges and when, the pooling depth,
the restriction to development wells, and the pass marks themselves.

An earlier draft of this section set recall and precision thresholds against "the gold evidence
sets" as though they existed. They did not, which made both pass marks unmeasurable as written
and would have let the real thresholds be chosen later under cover of having pre-registered
something.

## 16. The split for the drilling-report layer

Section 10's temporal boundary governs the production record. It does not transfer here: the
drilling reports run from 1992 to 2018, most of them clustered in campaigns years apart from the
production the boundary was computed from, and a date cut would put whole wells on one side by
accident.

**The split is by well, and here it can be.** The drilling reports cover 26 wellbores belonging
to 11 distinct wells, enough that holding out whole wells leaves something on both sides. The
production record's six producers are not the reason; they are a different layer with a
different split, and an earlier draft cited them here as though they justified this choice.

**The rule, and the sort it uses.** The hold-out is the four wells whose canonical names sort
last in byte order over the canonical string form, which is the ordering Python's `sorted`
gives and the one `splits.py` already uses elsewhere. Naming the sort is not pedantry: read as
a natural ordering, where `F-15` follows `F-9`, the same sentence selects F-11, F-12, F-14 and
F-15 instead, holds out 44 percent of events, and strips every retained production producer out
of the development set. One rule, two readings, opposite outcomes.

Applying it gives `15/9-F-4`, `15/9-F-5`, `15/9-F-7` and `15/9-F-9`, leaving seven development
wells. Every wellbore of a hold-out well goes with it, so `15/9-F-9 A` is held out with
`15/9-F-9`: a sidetrack shares its parent's campaign, its crew and often its problems.

**What the rule produced**, recorded after fixing it rather than used to revise it: 3,673
non-productive events in total, of which 616 are on hold-out wells: 16.8 percent. That is
lighter than the production split's 25 percent, and of the 330 possible four-well splits only
ten are this light.
The rule was fixed first; the alternative is choosing wells until the proportion looks right.

**Three consequences worth stating plainly rather than discovering later.**

The two hold-outs are disjoint. `15/9-F-4` is injection only, `15/9-F-7` and `15/9-F-9` do not
appear in the production record at all, and `15/9-F-5` has no production development days and is
already excluded from production hold-out scoring as a cold start. So no well is scored on both
layers, and cause attribution is generalised largely on a water injector and two wells the
production record never saw. That is what a by-well rule fixed in advance produced, and it
limits what a joint claim about the two layers could mean.

The development wells include 155 reports dated after the production boundary of 25 July 2014,
on wells whose production hold-out is scored. Labelling causes from a 2015 report on 15/9-F-12
means reading narrative about a period the production detector is scored on. Section 10 permits
profiling over the whole record as structural exposure while forbidding fits, labels and
threshold choices on post-boundary data, and a label read from a post-boundary drilling report
is a label, not profiling. **Labels, few-shot examples and prompt iteration therefore use
development wells and pre-boundary reports only.** Reports after 25 July 2014 on development
wells are available for extraction at run time and are not labelled or shown to a prompt.

The hold-out label budget is fixed here, not later: 60 events, drawn by the same stratified rule
as the development sample. Leaving it open would make the final scoring's sample size a free
parameter chosen once the development results were known.

## 17. Where the cause labels come from

The labels this protocol scores against are **produced by a language model**, specifically
`claude-opus-5`, applying `docs/labelling_guide.md` to each comment. They are recorded as
`label_source: machine_assisted` on every row of `labels/development_pass1.jsonl`, and that file
is published in full.

### 17.1 Why, stated plainly

Sections 14.3 to 14.6 were written on the assumption of a human labeller, and the guide still
describes one. The project's author does not have drilling-operations experience and cannot
assign a cause to a 1997 activity comment. Three routes were available.

The author could have labelled anyway. That produces a label set with a human's name on it and a
non-expert's judgement inside it, which is worse than the present arrangement rather than better,
because the provenance would invite exactly the confidence the labels cannot support.

A domain reviewer could have been engaged. That remains the right answer and is what section 17.4
specifies; it was not available for this phase.

The model could label, with the provenance stated and the pass marks that depend on it withdrawn.
That is what happened.

### 17.2 What it costs

The cost is the cause-attribution selection gate, and it is a real cost rather than a formality.

An extraction approach scored against these labels is being compared with a labeller of its own
kind. Where it agrees, the agreement may be about what the comment says or it may be about a
convention the two share, and the score cannot separate those. A 20 percent macro-F1 margin over
`echo-subcategory` earned on these labels is therefore not evidence that an approach reads
drilling narrative well. It is evidence that it reproduces this guide's application of this
taxonomy more closely than a lookup table does, which is a narrower claim and is the only one
that will be made.

The two baselines are not contaminated by this. Both are deterministic tables fixed in section
14.4 before any label existed, and both are exempt from amendment. So the comparison is between a
reading approach and a fixed opponent, and the opponent is honest. What is contaminated is the
target.

### 17.3 What still gates, and why each one survives

1. **Section 14.3, event detection and duration.** Checked against the source XML. The cause
   label does not enter either.
2. **Section 14.5 condition 3, span validity at 100 percent.** A span either is a substring of
   the comment it cites or it is not. Mechanical, and a fabricated citation is as serious whoever
   assigned the cause beside it.
3. **Section 14.5 condition 4, abstention.** The approach is compared with itself, run with and
   without `not_stated` permitted. The labels set which events count toward the coverage floor,
   so the condition is not wholly independent of them, and it is reported with that noted.

**What this leaves, said plainly rather than left for a reader to notice.** Both surviving gates are
conditions an approach controls unilaterally: condition 3 is satisfied by copying a substring, and
condition 4 compares the approach with itself. So while the suspension holds, the cause-attribution
layer has **no gate that can fail for being wrong about a cause**. That is the cost restated in its
sharpest form, and it is why `approach_is_selected` in `src/volve_ops/extraction/scoring.py` returns
false whenever any condition is suspended, rather than taking the conjunction over the survivors. A
two-condition bar made of self-checks is not a weaker version of the four-condition bar. It is not a
bar.

### 17.4 What would restore conditions 1 and 2

Named now, so that it cannot be defined later to fit whatever is available.

A reader with drilling-operations experience adjudicates a stratified subsample of **40 events**,
drawn by the same rule the guide fixes for its re-label subsample: half from events whose machine
label is `equipment_failure`, `equipment_maintenance` or `rig_service`, where the guide predicts
disagreement, and half at random from the rest. The adjudicator works from the comment, the
activity code, the state, the detail state and the timestamps, which is section 14.2's permitted set,
and sees neither the machine label nor the baselines' predictions.

The size, the strata and the seed, **20261006**, are fixed here, and `scripts/draw_adjudication.py`
performs the draw now rather than when an adjudicator is available. A subsample whose size or seed
is chosen once someone is ready to label it is a subsample chosen after seeing what it produces. The
worksheet it writes carries exactly section 14.2's permitted set and no machine label, so field-level
blinding is a property of the artifact rather than an instruction.

**Which guide the adjudicator is given, because the current one contains the answers.** The
labelling guide now carries a "Conventions the first pass had to settle" section, written after
labelling, which describes how several of the drawn events were resolved and quotes their comments.
Handing that to an adjudicator would measure whether they read it. The adjudicator is therefore given
the guide **as it stood at the `prereg-v2` tag**, `git show prereg-v2:docs/labelling_guide.md`, which
is the version that predates every label. If a later version fixes the rule 1 defect that amendment
3 records, the adjudicator is given that fix as a stated rule and still not the conventions section.

**The statistic, and the interval, because a bare point estimate at n=40 would contradict section
14.5 condition 2.** Raw agreement is the headline, and Cohen's kappa is reported beside it, because
`not_stated` runs above half the sample and raw agreement on the random half is partly free. A 95
percent Clopper-Pearson interval is reported with both. The decision rule is **both** of: raw
agreement at least 0.80, and the interval's lower bound at least 0.70. One number at n=40 moves about
12 points either way, and a protocol that demands a bootstrap interval of the condition it suspends
while accepting a point estimate from the condition that restores it is inconsistent with itself.

Two limits of this design, named rather than discovered. The subsample is 40 because it is a budget
on an unpaid domain reader's attention, not because 40 is sufficient. And one adjudicator yields no
estimate of their own reliability, which is the quantity amendment 2 withdrew inter-pass agreement
for failing to supply; a second adjudicator on an overlapping subset would supply it and is not
promised here.

Two numbers come out, and both are published whatever they say: the adjudicator's agreement with
the machine labels on those 40 events, and a per-class breakdown over the classes the subsample
reaches. Conditions 1 and 2 are restored as gates only if agreement is at least **80 percent**
overall. That figure is fixed here, before any adjudication, and it is not the pass mark for the
extraction system. It is the threshold at which the label set is worth scoring one against.

Below 80 percent the labels are republished as a convention-conformance set and the cause
attribution layer ships without a selected approach, exactly as section 14.5's closing paragraph
already provides for. Per-well NPT totals by category and duration do not depend on any of this
and remain reportable.

### 17.5 What is recorded, so that a reader can check rather than trust

Every label row carries the applied precedence rule from the guide alongside the cause and the
span, and a free-text note wherever the choice was close. Of the 135 published rows, 55 carry such a
note and 14 of those name a taxonomy label other than the one assigned, which is the computable
proxy for "considered and rejected" and is reported as that rather than as a judgement about intent.
This does not make a model-produced label an expert one.

**One deviation from section 14.2 in the labelling pass, disclosed because section 14.2 exists to
make exactly this checkable.** The pass saw the wellbore identifier alongside the permitted set. A
wellbore name carries the era: the `15/9-19` wellbores are 1990s exploration and the `F-` wellbores
are 2000s development, and era plausibly moves a cause label. It is not known whether it did. The
adjudication worksheet withholds it, so an adjudication is scored against labels made with slightly
more context than the adjudicator had, in the direction that disfavours agreement. It makes each label falsifiable by a reader who has the
knowledge the labeller lacked, which is the most this arrangement can offer.

Two things that will not be reported, because they cannot be measured here. **Inter-pass
agreement**, withdrawn by amendment 2 above. And the **anchoring rate**: an earlier plan had the
model recommend a label and the author accept or override it, so that the override rate would
measure how much the recommendation moved the human. With no human in the loop there is no
override rate, and a figure computed from a second model pass would not be one.

## 18. The investigation layer

Fixed before any investigation has been run, on a repository where the deterministic expectation
engine, the episode detector and the extraction layer already exist and are measured.

**One disclosure about what was known when this was written.** The sensor-coverage study in
`docs/data_profile.md`, including the finding that downhole pressure is usable on under a third of
`15/9-F-12`'s producing days, was carried out immediately before this section and committed
immediately after it. Section 18.2 below cites it. So this section was written knowing how much
pressure data exists, which is what made an unavailable mandatory channel worth making a stop
condition. It was not written knowing any investigation's output, because none had been run. What follows
judges the layer that reads an episode and tries to explain it.

### 18.1 What an investigation is, and what it may not be

One investigation answers one question: why did well X underperform during episode Y, where the
episode comes from the section 9 detector and not from a model's choice of interesting period. A
model picking its own episodes would be selecting the cases it can explain.

The controller owns the stages and the stop conditions. The model's judgement is exercised inside
them, and there is no stage at which the model is asked what to do next from an open list of tools.

**Which judgements, corrected by amendment 4.** This section originally named four: which hypothesis
needs more evidence, how to phrase a retrieval query, which report section to read, and whether
another evidence pass is justified. The implementation exposes **two**, the query and the decision to
continue. Which hypothesis is queried next is taken by the controller, in a fixed order over the
hypotheses still worth testing, and "which report section to read" does not exist because the
retrieval unit is a single activity comment rather than a sectioned document. A narrower judgement
surface is a stronger version of this section's claim, not a weaker one, but it is a difference
between what was registered and what was built, and it is recorded rather than quietly absorbed.

**How much the trace checks, stated precisely.** The stage of every step is recorded, and a sequence
the declared controller could not have produced is refused: a once-only stage repeating, stages out of
order, retrieval before any hypothesis exists or after the finding is composed. What that is worth is
narrower than it first appears, and independent review was right to press on it. The controller
assigns the stage labels itself and the step carries no tool identity, so the check cannot detect a
controller that did something else and labelled it correctly. It is a guard against this controller
changing into an unbounded one, enforced on every run, and not a proof that the current one is bounded.
The proof of that is the code, which a reader can read. Making the trace itself sufficient would need
the step to record the tool called rather than a stage name the caller chose, and that is not done
here.

### 18.2 The mandatory diagnostic bundle, and what happens when it is unavailable

Before any hypothesis is formed, these are retrieved deterministically: on-stream hours, choke
setting and its differential pressure, downhole and wellhead pressure, water cut and gas-oil ratio,
an offset comparison against the other producing wells over the same dates, and the day-class and
quarantine flags from section 6.

**Availability is data, not a detail.** `docs/data_profile.md` records that downhole pressure is
usable on 31.2 percent of `15/9-F-12`'s producing days and on none of `15/9-F-5`'s, where a
presence check reports 99.8 percent and nothing. So the bundle is defined with an explicit
availability record per channel, computed by `src/volve_ops/domain/sensors.py`, and every finding
publishes it. An investigation that reached a conclusion without a channel must say which channel it
lacked, in the finding, not in a log.

A channel is **mandatory** when the hypothesis under test depends on it. A hypothesis whose
mandatory channel is unavailable may not be marked supported, whatever else is present. It is marked
`unresolved` with the missing channel named. This is the one place the protocol forbids an inference
rather than scoring it, because a pressure-driven explanation asserted on a well with no pressure
data is not a weak conclusion, it is an unfounded one.

### 18.3 Stop conditions, all four of them explicit

An investigation ends when exactly one of these first becomes true, and the trace records which:

1. `evidence_threshold_met`: every open hypothesis is supported or contradicted.
2. `evidence_exhausted`: a retrieval pass returned nothing not already in evidence.
3. `mandatory_evidence_unavailable`: a channel the leading hypothesis requires does not exist for
   this well and period.
4. `step_budget_reached` or `cost_budget_reached`.

A budget breach is a reported incident, not a silent truncation. A finding produced under condition
3 or 4 carries that fact in the finding itself, because a conclusion reached because the money ran
out is a different object from one reached because the evidence settled.

### 18.4 Causal levels, and what each permits saying

Three levels, and the wording each licenses is fixed here so that it cannot drift upward later:

| level | what it requires | what may be said |
|---|---|---|
| `proximate_driver` | a deterministic channel shows the mechanical immediate cause | "Proximate driver identified: choke reduction." |
| `supported_mechanism` | the proximate driver plus a physical account consistent with the other channels | "Mechanism supported: drawdown fell with choke, and water cut did not move." |
| `documented_root_cause` | a cited document says why the operational change was made | "Root cause documented: planned choke reduction for gas-lift reallocation, per report X span Y." |

**"Root cause identified" is forbidden at the first two levels.** The permitted output is the one
the handoff states plainly: proximate driver identified, root cause unresolved, with the reason the
reports do not explain it. A system that rephrases a choke observation as a root cause has not
reached a stronger conclusion, it has made a weaker one sound stronger.

### 18.5 The provenance hard gate

A finding is blocked, not scored, when any of the following holds:

1. A cited fact id is not in the ledger, or its lineage does not reach measured facts.
2. A cited evidence span is not a verbatim substring of the document version cited.
3. A quantitative claim in the narrative has no corresponding fact or derived fact.
4. A hypothesis is marked supported while a mandatory channel it depends on is unavailable.

Blocked means the finding is not published and the investigation is recorded as failed. One
fabricated citation is one too many, for the same reason section 14.5 condition 3 is a gate rather
than a score.

### 18.6 The baseline, fixed here and exempt from amendment

**`strongest-deviation`**, deterministic and reading nothing. For the episode window it ranks the
mandatory channels by standardised deviation from the well's own stable reference window, names the
largest as the proximate driver, and always reports `documented_root_cause` as unresolved. Where a
channel is unavailable it is skipped rather than imputed.

**Its threshold is part of its definition and is stated here**, because an exemption a reader cannot
check is not an exemption: the baseline names a channel only when the movement reaches **1.0** of the
baseline window's own standard deviation, and abstains otherwise. The baseline window is the **60**
producing days of the well's own record immediately before onset. Amendment 4 records that both
numbers were fixed after v4 was tagged; they cannot move again.

This is not a straw opponent, which is the point of naming it before any investigation runs. A great
deal of well underperformance really is explained by on-stream hours or choke position, both of which
are in the structured data, and an agent that reads documents has to be shown to add something beyond
noticing the biggest number. Like the section 3 and 14.4 baselines, it cannot be amended: a baseline
that can move after results exist makes a relative pass mark meaningless.

### 18.7 Pass marks that gate now

1. **Provenance validity is 100 percent.** Every published finding passes 18.5. A gate, not a score.
2. **Stop-condition honesty is 100 percent.** Every finding's recorded stop condition matches the
   controller state that produced it, and every finding reached under conditions 3 or 4 says so.
3. **Trace replay is exact.** Replaying a recorded trace reproduces the same finding, byte for byte,
   including its verdict and every citation. A trace that does not replay is not evidence of what
   happened.
4. **Abstention is reachable and used.** `insufficient_evidence` must be a reachable verdict on the
   development episodes, demonstrated on at least one, and the conditions under which it is returned
   must be the recorded stop conditions rather than a model's unexplained reticence.
5. **No forbidden wording.** No finding below `documented_root_cause` contains a root-cause claim,
   checked mechanically against the level.

### 18.8 Pass marks that are deferred, and exactly why

**Whether an explanation is correct is not scored in this version, and no threshold is invented for
it.** Scoring that needs someone who can say whether a choke reduction explains a shortfall on a
specific North Sea well, and section 17 records that this project does not have that person. Writing
a number here that nobody can apply would be the failure mode this document exists to prevent.

What a later version must fix, pushed before any correctness figure is reported: how an episode's
reference explanation is established and by whom, the agreement statistic and its interval, the
treatment of partially correct explanations, and the pass mark against `strongest-deviation`. Until
then the layer reports its verdict distribution, its citation counts, its stop-condition
distribution, and its agreement with `strongest-deviation` on the proximate driver, all without a
pass mark.

Note what this means and does not mean. The gates in 18.7 are real and an implementation can fail
them. None of them can fail because an explanation is wrong, exactly as section 17.3 records for the
cause layer. That is the second time this limitation has bitten, it has the same cause both times,
and it is stated twice rather than mentioned once.

### 18.9 The Phase 3 gate

Five development investigations, including at least one `insufficient_evidence`, each verified
against raw evidence. Verification splits in two and the halves are not equally strong:

- **Mechanically verifiable, and required:** every cited fact resolves to the row it claims, every
  span is verbatim in the document cited, every number in the narrative has lineage, the stop
  condition matches the controller state, the trace replays exactly, and the wording matches the
  causal level. All of this is checked by a committed script.
- **Not verifiable here:** whether the explanation is right. Recorded as unverified rather than
  presented as verified.

The hold-out is not investigated in this phase. Section 10's rule stands: it is scored once, in
Phase 8.

## 19. The evaluation harness

Fixed before the harness exists. Section 18 was tagged without a single numeric threshold and
amendment 4 had to record nine of them afterwards; this section states its numbers, and where it has
none it says so rather than leaving a reader to find out from the source.

What this section judges is not a layer but the project's account of itself: whether every reported
figure is traceable to a frozen version, whether the hold-out really is untouched, and which of the
handoff's intended metrics this dataset and this project's circumstances actually permit.

### 19.1 The version freeze, and what a result is

A scored run records all of the following, and **a result quoted without a complete manifest is not a
result**. This restates section 12 for the evaluation layer and names the fields:

```text
dataset_version          the source files and their checksums, per docs/data_manifest.md
label_set_version        the cause-label file and its provenance, per section 17
parser_version           ingest
extractor_version        drilling-report extraction
investigator_version     the investigation controller
retrieval_index_version  the index build and its chunk count
correction_store_version the corrections in force, or `none`
model_roles              each semantic role mapped to a model, or `none` where no model is called
commit                   the repository state
```

**Pass mark, gating: every field is present and non-empty on every scored run, at 100 percent.** A
field whose value is legitimately absent records `none` rather than being omitted, because an omitted
field and a field that is deliberately empty are different claims and a reader cannot tell them apart.

**Pass mark, gating: a run repeated on unchanged inputs produces an identical manifest hash.** A
version freeze that does not reproduce is a record of nothing.

### 19.2 The leakage audit, which gates

The Phase 4 gate is "dev results table; hold-out untouched", and untouched is a claim that should be
checked rather than asserted. Five checks, each mechanical, **all gating at 100 percent**:

1. No hold-out well, as section 16 fixes them, contributes to any model fit, any threshold choice or
   any labelled event.
2. No report dated after the section 10 production boundary of 25 July 2014 appears in the labelled
   sample, on any well.
3. Every scored development figure derives from a day set that the split filter produced, not from one
   filtered afterwards. Filtering after the fact is how a hold-out day reaches a fit through a path
   nobody audited.
4. The correction store version recorded on a scored run contains no correction derived from a
   hold-out event.
5. No hold-out episode has been investigated, and no hold-out label file exists.

A failure here is an incident, not a score: the affected result is withdrawn rather than reported with
a caveat.

### 19.3 The development results table

One table, consolidating every measured figure in the project, and every row carries three things
beyond its value: the **denominator**, because `docs/data_profile.md` has already produced one figure
that differs by two points depending on which population it is taken over; the **status**, one of
`gated`, `reported` or `deferred`; and for a deferred row, **what would settle it**.

**Pass mark, gating: every published figure in the repository appears in the table, at 100 percent.**
Checked by the harness against the run manifests, not by reading the documents. A figure quoted in a
document and absent from the table is either stale or unreproducible, and both have happened in this
project already.

### 19.4 Calibration: bands, not probabilities, and the reason

Section 7.7 of the plan permits evidence-strength bands instead of a numeric probability where the
sample is too small. **It is too small, and by a wide margin: fourteen development episodes.** A
calibrated probability from fourteen outcomes would have a 95 percent interval roughly 25 points wide
in each bin, which is not a calibration.

So the harness computes an **evidence score** from observable features only, never from a model's
stated confidence, and reports bands:

| band | evidence score |
|---|---|
| `high` | at least 0.70 |
| `moderate` | 0.40 to 0.70 |
| `low` | below 0.40 |

The score is the mean of these six features, each scaled to the unit interval and all computable
without a model: the strongest standardised channel movement, capped at three standard deviations; the
number of mandatory channels available, over the number required; whether a documentary cause was
cited; the count of contradicting evidence, inverted; the fraction of the episode window that is
neither quarantined nor missing; and whether the run was curtailed.

**No pass mark, and no outcome rates, and the reason is the one section 18.8 already gave.** Bands are
calibrated against whether the conclusion was right, and nobody available to this project can say
whether it was. What is reported is the band distribution and its relationship to the things that can
be measured: verdict, stop condition, citation count. **What a later version must fix, before any
calibrated figure is reported:** the outcome definition, who determines it, the calibrator, and the
interval. Reporting a reliability diagram against outcomes this project assigned to itself would be
the labelling problem of section 17 wearing a statistician's hat.

### 19.5 The false-root-cause rate, split into the half that can be measured

Section 7.6 of the plan calls this the important safety metric, and it is, which is why it is worth
separating cleanly rather than reporting one number that mixes the two halves.

**The mechanical half gates.** A finding at `documented_root_cause` whose cited spans contain no
stated reason is a false root-cause claim detectable without domain knowledge, because the claim is
about the document rather than about the well. **Pass mark: zero such findings, at 100 percent.**
Likewise zero findings that claim a root cause in prose below the level that licenses it, which
section 18.7 already gates and which is counted here too so the safety metric is in one place.

**The half that needs a domain reader is deferred**, with the same wording as section 18.8: a finding
whose documented root cause is cited correctly and is nonetheless the wrong explanation cannot be
detected here. What a later version must fix: who adjudicates, on what sample, and the pass mark. The
asymmetry the plan asks for is recorded now so it cannot be chosen later: **a false confident
root-cause claim counts against the system more heavily than an abstention**, at a ratio fixed here of
**five to one**, and an unnecessary abstention counts against it at **one**.

### 19.6 Risk and coverage, deferred for the same reason, with the shape fixed

A risk–coverage curve plots error rate against the fraction of cases the system chose to answer, and
error rate needs correctness. Deferred. Fixed now so the axes cannot be chosen to flatter a result:
coverage is the fraction of episodes with a verdict other than `insufficient_evidence`; risk is the
fraction of those whose conclusion the adjudication of section 19.5 finds wrong; and the curve is
traced by varying the evidence-score band required to answer. The three bands of section 19.4 give
three points, which is a curve only by courtesy, and the report says so.

### 19.7 Trajectory, stability and cost, which are measurable now

All reported, none gated except the first:

- **Repeated identical tool calls: zero. Gating.** A controller that asks the same question twice has
  a defect, and this is cheap to check from the trace.
- Steps per investigation, and the distribution of stop conditions.
- Verdict and hypothesis stability over repeated runs. With no model called this is exactly 1.0 by
  construction, and the report states that rather than presenting determinism as a result.
- Tokens and cost. Zero while no model is called, and reported as zero rather than omitted.
- Early-exit reason distribution, which section 18.3 already produces.

### 19.8 The prose judge, specified and not run

Section 7.9 of the plan confines a model judge to prose quality and never to correctness. The rubric
is fixed here so that it cannot be written to match whatever a judge happens to score well:
**clarity**, whether a reader can state the finding's conclusion after one reading;
**structure**, whether the conclusion, the evidence and the limitation are separable;
**actionability**, whether the recommended next check is specific enough to carry out.
Each scored 1 to 5.

Not run, for a plain reason: no model provider key is configured in this project. Validation would
also need a human's own scores on a sample to measure agreement against, and **prose quality is the
one thing in this project the author can judge without drilling-operations experience**, so this is
deferred on the key rather than on the limitation of section 18.8. What a later version must fix: the
sample size, the agreement statistic, and the threshold below which judge scores are not reported at
all.

### 19.9 Data-quality tests

The eight checks of plan section 7.1, each gating at 100 percent except where noted: coverage against
the manifest, unit validity, alias and well-name resolution, zero-versus-missing behaviour per the
sentinel rule, duplicate detection, chronology, parse failures quarantined rather than dropped, and
the leakage checks of section 19.2. Coverage is reported rather than gated, because what fraction of a
channel exists is a property of the dataset and not a defect in this code.

### 19.10 CI, and what may spend money

**Free CI, on every push and pull request, and it must pass with no API key:** unit tests, parser and
schema tests, domain services, the provenance gate, the leakage audit, the version-freeze
reproducibility check, and the security invariants that already run.

**Paid evaluation, manually triggered only:** anything that calls a model. It may not run on a push,
on a pull request, or on a schedule. A scored hold-out run is manual, once, and in Phase 8.

**Pass mark, gating: the free workflow does not read any model credential.** Checked by the absence of
the secret from the workflow rather than by inspection of the code, because a workflow that cannot see
a key cannot spend one.

### 19.11 What this section does not do

It does not score the hold-out, which section 10 reserves for Phase 8 and which section 19.2 gates
against touching.

It does not create the curated episode set that plan section 7.3 would need for detector precision and
recall. Fourteen episodes from one detector on two wells is not a benchmark, and manufacturing
precision from it is the failure this document exists to prevent. Deterministic invariants and the
section 19.3 table stand in its place, and the limitation is reported wherever an episode figure
appears.

It does not report an end-to-end correctness figure, for the reason given three times now in three
sections, which is the honest number of times to give it.
