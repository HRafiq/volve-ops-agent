# Drilling-report extraction: what the deterministic layer produces

Produced by `scripts/run_extraction.py`, which is committed, alongside a run manifest carrying
the store version, the content hash and the parser and extractor versions.

No cause attribution exists yet. This document covers the deterministic layer only: what counts
as a non-productive event, how much of it there is, and what the two fixed baselines predict.
The pass marks that will judge an attribution approach were fixed in protocol v2 before any of
this ran, and are not restated here.

## What was extracted

1,759 drilling reports yield **3,673 non-productive events** across 11 wells and 26 wellbores,
totalling **8,563 hours**, or 357 days, of non-productive time.

The rule is the union protocol section 14.1 settled: an `interruption` activity head, or a
`fail` state. The two do not coincide:

| activity head | events |
|---|---:|
| interruption | 3,577 |
| drilling | 70 |
| plug abandon | 13 |
| formation evaluation | 13 |

The 96 events outside `interruption` are mostly failed casing runs and failed drilling. A failed
casing run is lost time whatever it was filed under, and an earlier draft of the protocol that
used the interruption head alone would have made counting any of them a parser defect.

Nothing was flagged for review: no event has a negative duration, and no comment is empty. The
labelling guide's empty-comment clause governs an empty set, which is recorded there.

## What the baselines predict

Both read nothing. Both are fixed in protocol section 14.4, with their mapping tables, and are
exempt from amendment.

| baseline | attributes a cause | abstains |
|---|---:|---:|
| echo-subcategory | 2,147 of 3,673, 58% | 1,526 |
| echo-statedetail | 1,766 of 3,673, 48% | 1,907 |

**They agree on only 36% of events.** That is the practical reason both are named. Naming only
`echo-subcategory`, as an earlier draft did, would have left the free signal in
`stateDetailActivity` unopposed: it marks 1,535 events `equipment failure` outright, and a
candidate could have cleared the bar without beating it. Because baselines are exempt from
amendment, adding the second one later would not have been possible.

Neither is degenerate. Both can abstain, so neither scores zero on the largest class, and
neither can be beaten by predicting one label everywhere.

## What is stored, and how it stays traceable

Events are written to a versioned store: one directory per extractor version, never overwritten.
A version rewritten in place has a manifest describing something other than its contents, and
every result traced to it becomes a guess, so a second write to an existing version is refused.

Each version carries a content hash computed over the events themselves, independent of the
order they were written, so a changed digest means changed content rather than a differently
scheduled directory walk. `verify()` recomputes it.

Event ids derive from the event's own content rather than from extraction order. A re-run on
unchanged reports produces the same ids, which is what lets a correction stay attached to the
event it corrected.

## The labelling sample

Drawn stratified and seeded, per the labelling guide, so the draw can be regenerated and checked
rather than taken on trust.

| split | drawn | eligible |
|---|---:|---:|
| development | 135 | 2,538 |
| hold-out | 60 | 616 |

The development pool is 2,538 rather than 2,961 because protocol section 16 excludes reports
dated after the production boundary even on development wells. A label read from a 2015 report
on a well whose production hold-out is scored is a label, not profiling, and section 10 permits
profiling over the whole record while forbidding labels on post-boundary data.

Stratification is by activity subcategory, across 20 of them. A proportional draw would give
`well control`, 29 events in the whole corpus, a good chance of appearing zero times, and the
taxonomy class it maps to would then be unscoreable.

## What this does not yet tell you

Nothing here measures a system. The deterministic layer is arithmetic and parsing, and its two
pass marks are exactness rather than skill. The question protocol section 14 exists to answer,
whether reading a comment adds anything over restating the label beside it, needs the labelled
sample, and the labels need a human.
