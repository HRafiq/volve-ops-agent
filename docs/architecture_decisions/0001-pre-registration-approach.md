# ADR 0001: pass marks are relative to named baselines, and the protocol is versioned

Date: 2026-10-04
Status: accepted

## Context

The project's claim is evaluation discipline: criteria fixed before the runs they judge,
a hold-out scored once, and a public history that evidences the ordering. That claim
creates a problem at the very start.

Several numbers have to be fixed before any data is inspected. The expectation engine
needs a pass mark. Two feasibility criteria need thresholds. Rate normalisation needs a
guard. None can be sized well without knowing the data, and all can be bent by knowing
it.

Pick an absolute error target blind and one of two things happens. Set it loosely and
passing proves nothing. Set it tightly and failure says more about how noisy an offshore
allocation record is than about the engineering. Either way the number carries no
information for a reader.

Deferring the numbers until after profiling gives up the ordering claim the project
rests on.

## Decision

Pass marks are expressed relative to baselines named in advance. For the expectation
engine, the requirement is to beat the better of `naive-median28` and
`naive-persistence` by at least 10 percent relative WAPE, at three horizons, with
lower-tail calibration and per-well bias conditions alongside. The baselines are fixed
in `docs/eval_protocol.md` and are exempt from amendment, because a relative pass mark
means nothing if the baseline can move.

Failure has a defined outcome rather than an open question. If no candidate clears the
bar, `naive-median28` with an empirical interval becomes the expectation model and that
is the reported result. This removes the incentive to move the bar, because failing it
is survivable and publishable.

The fallback is `naive-median28` specifically, not whichever baseline scored better.
`naive-persistence` cannot serve as an expectation at all: after one day of reduced
rate, the reduced rate becomes the expectation, and sustained underperformance stops
being detectable. It stays in as a comparator only. A fallback that silently breaks the
detector would be worse than no fallback.

Almost everything is fixed in v0, and the deferral is deliberately narrow: one absolute
implausibility bound that comes from a published capacity figure, the labelling criteria for
the curated episode set, and the splits for layers whose units are not the production
calendar. None of the three is a statistic of this dataset. Tolerance judgements are not
deferred. A minimum episode
duration or a tolerated false-episode rate is a judgement about what is worth a
reviewer's attention, not a property of the data, and deferring it until after the
production curves have been seen would let it be sized to the episodes already visible
by eye. The next version may fill only the named blanks and may not change a v0 number.

## Consequences

The criteria can fail, and drilling plan reconstruction is expected to. That is the
intended behaviour.

A reader can check the ordering. The pre-registration version is pushed before any data is
retrieved and tagged `prereg-v0` in the same push, so the protocol and the empty data manifest
sit together at a fixed, publicly visible point with no dataset file anywhere in the tree.

The honest limit of that evidence: a commit date can be rewritten, so the tag establishes
what was written and that it preceded the data in the repository's own history, not an
independently notarised wall-clock time. Anyone wanting stronger proof should read the
ordering off the history rather than the dates.

Some thresholds will be badly sized, because they came from domain reasoning rather than
the data. Section 13 of the protocol handles this: a new version states the old value,
the new value, the reason, and whether the change came before or after the affected data
was inspected. Post-inspection amendments are labelled wherever the affected result
appears, so a reader can discount them.

The staged versioning needs explaining in the write-up, since "pre-registered in two
versions" invites the suspicion that the second version is where the convenient numbers
went. The defence is the narrow contract on what the second version may contain, plus a
public diff.

## Note on the calibration bounds

The lower-tail calibration bounds of 0.05 to 0.20 were reached from the detector's
behaviour: false-episode load scales roughly with the lower-tail rate, so twice nominal
is the ceiling, and half nominal makes the band too wide to detect anything.

A fixed two-sided coverage band around that interval was considered and rejected, for two
reasons. A symmetric band tests both edges when the detector only ever uses the lower one, so
a badly placed band could pass it. And any such width would have had no derivation behind it,
which is the defect this ADR exists to avoid: a threshold with no stated reasoning cannot be
told apart from one picked because it looked about right.

The criterion that replaced it, Clopper-Pearson interval containment, carries a sample-size
consequence worth recording. Containment inside bounds this narrow is unachievable below
roughly 80 evaluated days per well, and admits only a single observed count at 82, so a gate
set at 60 days would have failed every well in that range no matter how well calibrated it
was. The gate is therefore 150 evaluated days, where the admissible band runs from 0.093 to
0.133 and a well passes or fails on its calibration rather than on how much data it has.

## Alternatives rejected

Absolute pass marks fixed in v0. Rejected because a blind absolute threshold is
uninformative in both directions, and because it creates pressure to amend later for
reasons hard to distinguish from motivated reasoning.

All thresholds deferred until after profiling. Simpler, and it would produce
better-sized numbers. Rejected because it abandons the ordering claim for a modest gain
in calibration.

Profiling first and then writing v0 as if blind. Rejected as dishonest.
