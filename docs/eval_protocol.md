# Evaluation protocol

Version: v0
Date: 2026-10-04
Status: pre-registered. Pushed before the work it judges.

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
- Splits for the layers section 10 does not cover, named in section 10.

Anything else these definitions leave open is, when it is later set, an amendment under
section 13 and carries that label. That clause exists so the deferred list cannot be
extended by discovering a convenient gap in it.

None of the three deferred items is drawn from this dataset: one comes from a published
capacity figure, one from a labelling guide, one from calendar arithmetic. That is deliberate.
Had any of them been a data statistic, it would have had to be computed from pre-boundary
data only, because a threshold drawn from a whole-record profile is a threshold choice using
hold-out data, which section 10 forbids.

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

1. **Missing**, if on-stream hours is absent, or oil volume is absent, or well status is
   absent on a day where a status field exists. Excluded everywhere and flagged. Missing
   is never coerced to zero. Zero means measured zero. Per-row nulls are the normal case
   in a daily production record rather than an edge case, which is why a null status
   lands here instead of being read as "not producing".
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

Tightening a pass mark after seeing a result that failed it is not an amendment. It is
the failure mode this document exists to prevent.
