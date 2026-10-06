# ADR 0008: the drilling reports rarely overlap a production episode, and that bounds what an investigation can document

Date: 2026-10-06
Status: accepted
Supersedes: an earlier draft of this ADR, retracted below.

## Context

Protocol section 18.4 defines three causal levels. The top one, `documented_root_cause`, requires a
cited document saying why an operational change was made, and it is the only level permitted to claim
a root cause. The design points at it: the mandatory diagnostic bundle establishes what changed, and
retrieval over the drilling narrative is what would establish why.

Counting the 3,673 extracted non-productive events against the fourteen development episode windows:

| window | events across all 14 episodes | episodes with none |
|---|---:|---:|
| inside the episode | **0** | 14 of 14 |
| ±45 days | 8 | 12 of 14 |
| ±180 days | 22 | 10 of 14 |

Both windows with any overlap belong to the same well: `15/9-F-14`, January and March 2012. The reason
the rest are empty is visible in the per-year counts for the two wells that carry every episode:

| well | NPT events by year |
|---|---|
| 15/9-F-12 | 2007: 120, 2008: 84, 2014: 19, 2016: 37 |
| 15/9-F-14 | 2007: 25, 2008: 102, 2009: 1, 2010: 13, 2012: 4, 2016: 126 |

The episodes fall in 2009 to 2014. The reports cluster in 2007 to 2008 and again in 2016. That is not
an accident of this corpus: a daily drilling report is written when a rig is on the well, and a well
that is quietly producing has no rig. The documents describe drilling and intervention. The episodes
are periods of production.

## What the first version of this ADR got wrong

The first version concluded that `documented_root_cause` was **unreachable** and unreached *"for want
of source documents rather than for want of capability"*. Independent review showed that claim was
wrong twice over, and the corrections matter more than the original conclusion.

**The capability was never implemented.** No code path could assign `documented_root_cause`: the
hypothesis templates hard-coded the lower two levels, so the level was unreachable whatever the data
said. Attributing its absence to the dataset was therefore unfounded, and it was the kind of
unfounded claim this project exists to avoid making.

**The documents did exist, and retrieval never asked.** The controller phrased its queries only from
hypotheses already marked *plausible*, so the hypothesis a finding actually rested on was never put to
the documents. On `15/9-F-14` in January 2012 there are four reports inside the window, and the
retrieval stage recorded zero hits because it was asking about the wrong hypothesis.

Both are fixed. Retrieval now queries every hypothesis worth testing, supported ones included, and a
cited span that states a reason lifts a supported hypothesis to the documented level.

## What the corrected run shows

`documented_root_cause` is reached **once in fourteen episodes**, on `15/9-F-14` from 31 January 2012,
citing a report dated **30 January 2012**, one day before onset:

> "Closed in well to prepare for handover."
> "Waited for Production Department to prepare well for handover."

The choke reduction the structured data established is explained: the well was closed in and handed to
the Production Department. That is a documented root cause, cited verbatim, and the gate passes it.

Two document citations across all fourteen findings. One episode of fourteen reaches the top level.
Five reach `supported_mechanism`, three `proximate_driver`, and five reach no level at all.

## Decision

`documented_root_cause` stays defined, is implemented, and is reported as **rarely reachable on
production episodes because the documents rarely exist for them** — one episode in fourteen, and both
candidate episodes on one well.

Three consequences are accepted rather than worked around.

**The retrieval stage runs on every episode even though it usually finds nothing.** Each trace records
the query, the hits and how many were citable, which is what makes the limitation evidence rather than
an assertion. It is also the path the drilling-report layer will need, where documents genuinely exist.

**The window is named wherever the claim is made.** `EVIDENCE_WINDOW_DAYS = 45` is outcome-determining:
at 45 days 12 of 14 episodes have no report in range, at 180 days 10 of 14. The constant was chosen
after protocol v4 was tagged and is recorded in amendment 4 as a post-inspection parameter.

**No other document source is substituted.** The corpus holds per-well engineering documents and
completion reports. Reaching for them now would be choosing a source after seeing that the
pre-registered one came up nearly empty. Protocol section 15 already scopes retrieval to drilling
comments and those documents; widening the index is a protocol version with its own pushed commit, and
whether it helps is then a measurement rather than a hope.

## Consequences

The honest claim for a typical production episode is the one the design asked for in these words: what
changed, from data, and no report explains why. For the rare episode that abuts an intervention, the
reports do explain it, and the layer says so with a citation.

This is the third pre-registered capability this dataset has constrained, after B1 drilling plan
reconstruction and C1 allocation reconciliation, and all three are constrained the same way: Volve is
generous about measurements and thin about the operational record explaining them. A reader should
carry that into every conclusion here.

A process note worth keeping, because it is the most useful thing in this file. The first version of
this ADR reasoned from a real, correctly computed table to a conclusion that flattered the project: it
blamed the dataset for an absence the code was causing. The table verified; the inference did not. An
independent review that only re-checked the arithmetic would have passed it.
