# ADR 0002: recorded drilling time is reported as non-NPT recorded time, not productive time

Date: 2026-10-04
Status: accepted

## Context

When planned drilling durations cannot be reconstructed from source data, the fallback
is to report a time breakdown without a planning baseline. The obvious split is
productive time against non-productive time.

That wording claims more than the data supports. What can be computed is total recorded
time, minus classified non-productive time, minus time that could not be classified.
The remainder is time that was not recorded as a problem. It is not time positively
identified as productive work.

The distinction matters because the residual absorbs every gap in the source records.
Activity that nobody wrote up, time logged against a vague heading, and genuine drilling
progress all land in the same bucket. Calling that bucket "productive" turns a recording
artifact into an operational claim, and it is exactly the kind of quiet overclaim the
rest of this project is built to avoid.

## Decision

The category is named **non-NPT recorded time**.

The word "productive" is reserved for time that source records positively identify as
productive work, and is applied only to that portion. Where no such classification exists
in the source, the word is not used at all.

The three categories reported are non-NPT recorded time, NPT, and other unclassified
time.

## Consequences

The label is less familiar than "productive time" and a reader may need the interface to
explain it, so the interface states what the category is and is not.

The breakdown stays honest when source records are incomplete, which is the normal case
for daily drilling reports, and the size of the unclassified bucket becomes a visible
measure of how complete the records are rather than something hidden inside a
reassuring total.
