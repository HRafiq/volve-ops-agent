# ADR 0009: the investigation queue's priority rule reduces to shortfall and duration, and says so

Date: 2026-10-08
Status: accepted

## Context

The operator console's investigation queue needs an ordering, and the console design fixed three
things about it before any of it was built: the rule is deterministic, it is printed under the table
so a reader can recompute it, and a model never decides it. A queue ordered by a language model's
sense of importance is the failure this project exists to avoid.

The design left one question open and required it settled before implementation: whether a case in
which no single explanation is supported should score higher, on the argument that it needs more
human attention, or whether evidence strength should enter the rule some other way.

The starting rule, a placeholder in the design mockup, was:

- cumulative shortfall at or above 30,000 Sm3 scores 3, at or above 10,000 Sm3 scores 2, else 1;
- plus 1 if the episode lasts 40 days or more;
- plus 1 if review is pending;
- plus 1 if no single explanation is supported;
- 5 or more is HIGH, 3 to 4 is MEDIUM, 2 or less is LOW.

## What the data says

Two candidate forms of the disputed clause were scored against all fourteen development episodes.
The blunt form adds 1 whenever the verdict is not `supported_explanation`. The banded form adds 1
only when the verdict is unresolved **and** the section 19.4 evidence band is `high` or `moderate`,
the case where the evidence was there and the system still could not choose between explanations.

**Neither form changes the priority band of a single episode. 0 of 14 differ.** The bucket counts are
identical under both: 1 HIGH, 5 MEDIUM, 8 LOW.

The reason is visible once the terms are counted rather than argued about:

| term | episodes it fires on |
|---|---:|
| cumulative shortfall | 14 of 14, and it is the only term with three levels |
| episode lasts 40 days or more | 4 of 14 |
| review is pending | **0 of 14** |
| no single explanation supported | 7 of 14 blunt, 3 of 14 banded |

The review term is zero because no review state exists until an operator creates one, so on a first
run it can never fire. The unresolved term fires on half the queue under the blunt form, and in every
one of those cases the additional attention has nothing to act on: three are blocked by downhole
pressure that is absent for the whole episode, and the remaining four have no in-window document to
find, which ADR 0008 established is the normal case rather than the exception.

So **on this dataset the four-term rule reduces to shortfall plus duration**, and the two terms that
would make it a judgement about where a human is needed are either inert or pointed at cases nobody
can resolve.

## Decision

1. **The banded form is adopted**, because the case worth a human's time first is one where the
   evidence was strong and the system still could not choose. "No evidence, so no conclusion" is a
   data-coverage problem and belongs in a filter, not at the top of a review queue.
2. **The rule is published with its term counts**, exactly as tabulated above, every time it is
   printed. A four-term rubric of which two terms never fire reads as more considered than it is, and
   the console must not borrow that credibility.
3. **The console states that the rule is not validated.** Fourteen episodes, one of them HIGH, cannot
   show that an ordering is a good ordering. The rule is a stated convention, not a measured result,
   and the queue header says so.
4. **The thresholds do not move after this date.** 30,000 Sm3, 10,000 Sm3, 40 days and the 5 and 3
   cut-offs are fixed in protocol section 21 and pushed before the console renders anything. Tuning
   them against this dataset would be fitting a priority rule to fourteen cases.

## Consequences

The queue's default sort is priority, then cumulative shortfall. Because the rule reduces to those two
quantities here, that default is close to sorting by shortfall alone, and a reader comparing the two
orderings will find them nearly identical. That is the honest state of it.

The disputed clause cannot be validated on Volve. It would take a dataset with review history and with
episodes whose missing evidence is obtainable. Both are named in protocol section 21.7 as deferred,
with what would settle them.

What this ADR does not do is remove the clause. An inert term that is correct in principle is worth
keeping over one that is wrong in principle, because the next dataset may exercise it, and the
alternative is a rule that silently has nothing to say about human attention at all.
