# Expectation engine: measured performance

Every figure here comes from development data only. The hold-out, which begins on 2014-07-25
with a 90-day buffer before it, has not been fitted on, selected on, or looked at.

The candidate comparison and the selection rule were fixed in `docs/eval_protocol.md` before
any of this was run. Section 8 requires a candidate to beat the better of two named naive
baselines by at least 10 percent relative WAPE, at horizons of 7, 14 and 28 valid producing
days, and to satisfy per-well calibration and bias conditions.

## Result: no candidate passes

| model | WAPE H=7 | H=14 | H=28 |
|---|---:|---:|---:|
| choke-scaled | **0.0953** | **0.1077** | 0.1366 |
| naive-persistence | 0.1021 | 0.1096 | **0.1326** |
| exponential-decline | 0.1121 | 0.1197 | 0.1430 |
| hyperbolic-decline | 0.1121 | 0.1196 | 0.1427 |
| naive-median28 | 0.1172 | 0.1204 | 0.1392 |

2,597 evaluated days, across the four wells that have any stable reference window in the
development period.

The decline curves lose to a baseline that simply repeats yesterday's rate, by 8 to 10 percent.
The operating-condition-aware model is the best of the five at the short horizons, improving on
the better baseline by 6.6 percent at 7 days and 1.8 percent at 14, but it falls 3.0 percent
behind at 28 and the condition requires all three horizons. Nothing reaches the 10 percent bar
at any horizon.

So the fallback fires, and it was written in advance for exactly this: `naive-median28` becomes
the expectation model.

**It is deliberately not `naive-persistence`, which scored better.** After a single day of
reduced rate, persistence makes the reduced rate the expectation, so sustained underperformance
becomes undetectable by construction. The baseline that wins on error is the one that cannot do
the job, and a selection rule written after seeing this table would have been very tempted by
it.

## Calibration fails, and the cause is the interval not the data

| model | 15/9-F-12 lower-tail | 15/9-F-14 lower-tail |
|---|---|---|
| choke-scaled | 0.192, CI [0.138, 0.257] | 0.366, CI [0.292, 0.446] |
| exponential-decline | 0.346, CI [0.277, 0.420] | 0.236, CI [0.173, 0.309] |
| hyperbolic-decline | 0.341, CI [0.272, 0.414] | 0.236, CI [0.173, 0.309] |

The tolerated range is a Clopper-Pearson interval contained in 0.05 to 0.20. None of these is.

The intervals are built from a window's own residual quantiles and widened by the square root
of the horizon. That growth law is the simplest one that is not obviously wrong, and it is
stated rather than tuned, but it is clearly too slow: observed exceedance runs two to four times
nominal. Fixing it means modelling how the error of a carried-forward expectation actually
grows, which is work for the evaluation phase rather than something to tune until the number
comes out right.

Per-well bias passes on both qualifying wells, within 3.2 percent of mean rate.

Only two of the four wells reach the 150 evaluated days the calibration condition requires. The
protocol's own fallback for that case is a pooled check with its limitation stated.

## Known failure modes, observed rather than imagined

**A single expectation carried too far is not an expectation.** The first version of the sweep
fitted on one stable window and carried it across the rest of the record, up to 2,155 days for
15/9-F-12. Because the interval widens with horizon, the band became wide enough that nothing
could fall outside it and the detector found zero episodes on a field that visibly has some.
Section 7's rule that the expectation comes from the most recent window ending before the
candidate is not a detail; without it the detector silently stops working.

**Regime segmentation that cuts at the worst day instead of the step finds nothing.** The choke
test originally split a segment at the day furthest from the window median. For a clean step
change, where a well is choked back on a date and stays there, that is the first day, so the
algorithm peeled one day off at a time and never separated the two regimes. Cutting at the
largest step between consecutive readings fixes it, and the change moved real results: one well
gained an episode and another lost its only reference window.

**Decline curves lose to persistence on this field.** Arps curves are the standard expectation
for a producing well and both forms came in 8 to 10 percent worse than repeating yesterday.
Volve's producers are short-lived, frequently intervened, and operated against changing choke
settings, so a smooth decline through a reference window is not what the next four weeks look
like.

## Episodes opened on development data

Using the selected expectation, the detector opens four episodes across four wells:

| well | onset | offset | valid days | shortfall Sm3 | threshold Sm3 | deferred Sm3 |
|---|---|---|---:|---:|---:|---:|
| 15/9-F-12 | 2009-01-15 | 2009-01-27 | 13 | 14,133 | 10,617 | 267 |
| 15/9-F-12 | 2010-01-18 | 2010-05-04 | 103 | 153,881 | 80,439 | 24,031 |
| 15/9-F-12 | 2013-10-02 | 2013-10-26 | 25 | 5,764 | 1,991 | 593 |
| 15/9-F-14 | 2009-05-29 | 2009-06-16 | 19 | 12,183 | 11,606 | 4,768 |

Each clears its own volume threshold, which scales with the number of valid producing days in
the window so that a long episode faces a proportionally larger bar than a short one. Deferred
volume is reported separately from rate shortfall throughout: the second 15/9-F-12 episode lost
153,881 Sm3 while flowing and a further 24,031 Sm3 to downtime, and those are different
operational facts that should not be added together.

Two wells open no episodes because they have no stable reference window in the development
period at all, which for a field where half the producers arrived in 2014 is the expected
outcome rather than a failure.

These are candidate episodes from a deterministic detector. Nothing here says why any of them
happened.
