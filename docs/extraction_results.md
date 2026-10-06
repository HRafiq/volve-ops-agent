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
`stateDetailActivity` unopposed: it marks 1,555 of these events `equipment failure` outright,
1,535 of them under the interruption head, and a
candidate could have cleared the bar without beating it. Because baselines are exempt from
amendment, adding the second one later would not have been possible.

Neither is degenerate. Both can abstain, so neither scores zero on the largest class, and
neither can be beaten by predicting one label everywhere.

## What is indexed

3,673 narrative chunks, one per event comment, indexed lexically with BM25. That is the
`bm25-only` baseline protocol section 15 fixes, and for now it is the whole index.

Two things it does not yet cover, recorded so its scope is not mistaken for the section's.
Section 15 scopes retrieval to drilling-report comments **and** the per-well engineering
documents, and no programme or completion report is indexed. And only the comments on
non-productive events are chunked, which is 3,673 of the corpus's 23,447 activity comments; the
rest describe productive work, and no retrieval question yet asks about them.

## What is stored, and how it stays traceable

Events are written to a versioned store: one directory per extractor version, never overwritten.
A version rewritten in place has a manifest describing something other than its contents, and
every result traced to it becomes a guess, so a second write to an existing version is refused.

Each version carries a content hash computed over the events themselves, independent of the
order they were written, so a changed digest means changed content rather than a differently
scheduled directory walk. `verify()` recomputes it.

Event ids derive from the source document, the event's start time, its activity code, and its
position among the report's activity blocks. A re-run on unchanged reports produces the same
ids, which is what lets a correction stay attached to the event it corrected.

The limit is worth stating rather than discovering. Because the position counts every activity
block and not only the non-productive ones, inserting or removing any earlier block in a
corrected report changes the id of every later event in that report. Ids are stable across
re-runs of unchanged input, not across edits to a report.

## The labelling sample

Drawn stratified and seeded, per the labelling guide, so the draw can be regenerated and checked
rather than taken on trust.

| split | drawn | eligible |
|---|---:|---:|
| development | 135 | 2,538 |
| hold-out | 60 | 616 |

The development pool is 2,538 of the 3,057 events on development wells: protocol section 16
excludes reports dated after the production boundary even on development wells, and the date
cut removes 519.

An earlier version of this sentence gave the pre-cut figure as 2,961. That is the count under
the interruption head alone, which is the narrower rule section 14.1 exists to reject, and the
difference between the two is exactly the 96 fail-state events this document argues for
including two sections above. A label read from a 2015 report
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
