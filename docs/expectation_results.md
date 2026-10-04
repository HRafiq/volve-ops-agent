# Expectation engine: measured performance

Every figure here is produced by `scripts/run_expectation_study.py`, which is committed, and
written alongside a run manifest carrying the commit, the input checksums, the split and the
protocol version. A result that cannot be regenerated from the repository is not a result.

Development data only. The hold-out begins on 2014-07-25 with a 90-day buffer before it, and
the split is applied at the source rather than by remembering to filter at each call site.

The candidate comparison and the selection rule were fixed in `docs/eval_protocol.md` before
any of this ran. Section 8 requires a candidate to beat the better of two named naive baselines
by at least 10 percent relative WAPE at horizons of 7, 14 and 28 valid producing days, and to
satisfy per-well calibration and bias conditions at every horizon.

## Result: no candidate passes

| model | WAPE H=7 | H=14 | H=28 |
|---|---:|---:|---:|
| choke-scaled | **0.0984** | **0.1090** | 0.1321 |
| exponential-decline | 0.1200 | 0.1240 | 0.1367 |
| hyperbolic-decline | 0.1199 | 0.1239 | 0.1364 |
| naive-median28 | 0.1211 | 0.1233 | **0.1297** |
| naive-persistence | 0.1216 | 0.1236 | 0.1338 |

2,548 evaluated days across the three wells with any stable reference window in the development
period.

The operating-condition-aware model clears the 10 percent bar convincingly at the two shorter
horizons, improving on the better baseline by 18.7 percent at 7 days and 11.6 percent at 14. It
loses by 1.9 percent at 28, and section 8 requires all three. Both Arps decline forms gain about
1 percent at 7 days and lose at the longer two.

So the fallback fires, and it matters that it was written in advance: `naive-median28` becomes
the expectation model.

A note on what nearly happened. The choke-scaled model is the best short-horizon expectation by
a wide margin, and a selection rule written after seeing this table would have been very
tempted to drop the 28-day horizon or soften the all-horizons requirement. The reason not to is
not only procedural. A choke is often reduced *because* of a problem, so an expectation that
follows the choke absorbs the consequences of the very thing an investigation exists to find.
The model that scores best is the one most likely to explain away the episodes.

## Calibration fails, at every horizon, including pooled

Per-well containment, with the pooled fallback that section 8 specifies when fewer than half the
field's six producers reach 150 evaluated days. Only two do.

| model | H=7 pooled lower-tail | tolerated |
|---|---|---|
| choke-scaled | 0.302, CI [0.255, 0.352] | 0.05 to 0.20 |
| exponential-decline | 0.387, CI [0.337, 0.440] | 0.05 to 0.20 |

Nothing is contained, per well or pooled. The intervals come from a window's own quantiles and,
for the candidates, widen as the square root of the horizon. That growth law is stated rather
than tuned, and it is clearly too slow: observed exceedance runs two to four times nominal.
Modelling how the error of a carried-forward expectation actually grows is work for the
evaluation phase, not something to adjust until coverage comes out right.

The two naive baselines are excluded from that widening. Section 3 fixes their interval as the
empirical 10th and 90th percentile of rate over the trailing 28 valid producing days, and
section 13 exempts both baselines from amendment. An earlier version of this code widened them
along with the candidates, which was an undisclosed amendment to something the protocol says
cannot be amended, and because the selected expectation is one of those baselines it changed
the published episodes.

## Bias passes on the mean and fails on drift

Mean residual sits within 3 percent of mean rate for every qualifying well and model, well
inside the 5 percent bound. The split-half drift test that section 8 also requires fails
extensively: for the selected expectation and the candidates alike, dozens of half-windows
exceed the bound, with individual halves reaching 20 percent.

That combination is the diagnosis. A model can be unbiased across a reference window while
drifting badly within it, and the mean alone would have reported this expectation as unbiased.

## Known failure modes, observed rather than imagined

**An expectation carried too far stops being an expectation.** The first sweep fitted on one
stable window and carried it across the rest of the record, up to 2,155 days. With an interval
that widens with horizon, the band became wide enough that nothing could fall outside it and
the detector found zero episodes. Section 7's rule that the expectation comes from the most
recent window ending before the candidate is not a detail; without it the detector silently
stops working.

**Regime segmentation that cuts at the worst day instead of the step finds nothing.** Splitting
a segment at the day furthest from its median peels one day off at a time for a clean step
change, because that day is the first one. Cutting at the largest step between consecutive
readings separates the regimes, and the change moved real results.

**Widening a fixed baseline changes the answer.** Restoring the section 3 band took the episode
count from 4 to 14. An interval is not a presentation choice when a detector triggers on its
lower edge.

## Episodes opened on development data

| well | onset | offset | valid days | shortfall Sm3 | threshold Sm3 | deferred Sm3 |
|---|---|---|---:|---:|---:|---:|
| 15/9-F-12 | 2008-08-22 | 2008-09-10 | 15 | 15,074 | 6,869 | 20,625 |
| 15/9-F-12 | 2009-01-13 | 2009-03-08 | 55 | 54,366 | 44,920 | 6,796 |
| 15/9-F-12 | 2009-06-21 | 2009-07-18 | 28 | 45,680 | 20,300 | 0 |
| 15/9-F-12 | 2010-01-14 | 2010-05-27 | 130 | 215,077 | 101,524 | 24,031 |
| 15/9-F-12 | 2010-07-10 | 2010-08-06 | 28 | 18,819 | 10,706 | 372 |
| 15/9-F-12 | 2011-02-17 | 2011-03-11 | 23 | 6,141 | 4,933 | 0 |
| 15/9-F-12 | 2011-08-26 | 2012-03-12 | 151 | 31,623 | 28,201 | 35,939 |
| 15/9-F-12 | 2013-09-05 | 2013-12-05 | 87 | 18,646 | 6,929 | 5,348 |
| 15/9-F-12 | 2014-03-27 | 2014-04-25 | 29 | 1,566 | 1,147 | 758 |
| 15/9-F-14 | 2009-05-29 | 2009-08-02 | 66 | 95,904 | 40,316 | 7,442 |
| 15/9-F-14 | 2010-06-26 | 2010-07-12 | 17 | 8,977 | 6,553 | 170 |
| 15/9-F-14 | 2012-01-31 | 2012-03-03 | 33 | 11,627 | 8,010 | 225 |
| 15/9-F-14 | 2012-03-11 | 2012-03-27 | 17 | 3,911 | 3,186 | 165 |
| 15/9-F-14 | 2014-03-22 | 2014-04-06 | 16 | 1,591 | 1,433 | 1,801 |

Fourteen episodes on two wells. Each clears a volume threshold that scales with the number of
valid producing days in its window, so a long episode faces a proportionally larger bar. Gap
fractions are 0 or 1 percent throughout, so none is flagged as poorly evidenced. One is
open-ended, reaching the end of the development period.

Deferred volume is reported separately from rate shortfall throughout. The 2010 episode on
15/9-F-12 lost 215,077 Sm3 while flowing and a further 24,031 Sm3 to downtime; the 2008 one lost
more to downtime than to rate. Those are different operational facts and adding them would hide
which was which.

Four wells open no episodes: two have no stable reference window in the development period at
all, which for a field where half the producers arrived in 2014 is the expected outcome.

These are candidate episodes from a deterministic detector. Nothing here says why any of them
happened, and the calibration failures above mean the band they were detected against is
narrower than it should be, so this count should be read as an upper bound.
