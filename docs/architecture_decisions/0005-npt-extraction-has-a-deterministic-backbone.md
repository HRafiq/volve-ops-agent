# ADR 0005: NPT classification is deterministic; the model reads cause, not category

Date: 2026-10-04
Status: accepted

## Context

The original design for extracting non-productive time assumed the daily drilling reports would
give structured headers plus free-text remarks, and that an LLM would have to read those
remarks to decide both what kind of event occurred and how long it lasted. That assumption was
made before the reports were seen.

The reports are richer than that. Each one carries a sequence of activity blocks, 13.3 per
report and 23,447 across the 1,759 reports, and each block carries:

- `dTimStart` and `dTimEnd`, which give duration directly;
- `proprietaryCode`, a two-level activity code whose first level separates `drilling`,
  `completion`, `workover`, `plug abandon`, `moving` and `interruption`, and whose second level
  distinguishes, among others, `waiting on weather`, `maintain` and `other`;
- `state`, which is `ok` or `fail`;
- `stateDetailActivity`, which carries `success`, `equipment failure` or `operation failed`;
- `comments`, free text describing what actually happened.

## Decision

Non-productive time is identified deterministically, from the `interruption` activity head and
the failure states, with duration computed from the timestamps. The model is not asked which
category an event belongs to or how long it lasted.

The model's job is narrowed to the question the structured fields cannot answer: given an
interruption that the source has already classified and timed, what does the narrative say
caused it. Its output is a cause attribution with an evidence span, which the provenance gate
can check against the document, and which a human reviews.

## Consequences

This fits the project's thesis better than the design it replaces. Deterministic systems
establish the facts, which here include the category and the duration, and the model is left
with the part that genuinely needs reading comprehension. It also shrinks what an extraction
error can damage: a wrong cause attribution is visible and reviewable, whereas a wrong category
or duration would have silently corrupted every total built on it.

It changes what the extraction evaluation measures. Category accuracy against hand labels was
going to be a headline metric; it now measures the source's own coding rather than the system's,
so it becomes a data-quality check instead. The metrics that matter become cause-attribution
correctness and evidence-span correctness, and the labelling guide has to be written for those
instead. That guide is still written before any label is made.

A caveat worth recording: the activity codes are the operator's own, applied at the time by the
people filling in the reports, and nothing here validates them. An interruption that nobody
coded as one stays invisible, which is the recorded-versus-invisible lost time problem in a
concrete form. The system reports what the record says and does not claim to have found all
non-productive time.
