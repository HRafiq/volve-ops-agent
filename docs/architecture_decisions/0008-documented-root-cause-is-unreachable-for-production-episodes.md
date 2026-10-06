# ADR 0008: documented root cause is unreachable for production episodes in this dataset

Date: 2026-10-06
Status: accepted

## Context

Protocol section 18.4 defines three causal levels. The top one, `documented_root_cause`, requires a
cited document saying why an operational change was made, and it is the only level permitted to use
the phrase a reader trusts most. The whole design of the investigation layer points at it: the
mandatory diagnostic bundle establishes what changed, and retrieval over the drilling narrative is
what would establish why.

Running the layer over all fourteen development episodes produced **zero document citations** and
reached `documented_root_cause` **zero times**. The first reading was that retrieval was weak. It is
not. The documents do not exist.

Counting drilling-report events against the episode windows:

| window | NPT events across all 14 episodes | episodes with none |
|---|---:|---:|
| inside the episode | **0** | 14 of 14 |
| ±45 days | 8 | 12 of 14 |
| ±180 days | 22 | 10 of 14 |

Not one of the 3,673 extracted non-productive events falls inside any episode window. The reason is
visible in the per-year counts for the two wells that carry every episode:

| well | NPT events by year |
|---|---|
| 15/9-F-12 | 2007: 120, 2008: 84, 2014: 19, 2016: 37 |
| 15/9-F-14 | 2007: 25, 2008: 102, 2009: 1, 2010: 13, 2012: 4, 2016: 126 |

The episodes fall in 2009 to 2014. The reports cluster in 2007 to 2008 and again in 2016. That is
not an accident of this corpus: a daily drilling report is written when a rig is on the well, and a
well that is quietly producing has no rig. The documents describe drilling and intervention. The
episodes are periods of production.

## Decision

`documented_root_cause` stays defined in the protocol and is reported as **unreached, for want of
source documents rather than for want of capability**. No threshold is adjusted and the level is not
removed.

Three consequences are accepted rather than worked around.

**The retrieval stage still runs.** It is what produces the evidence of the limitation: each trace
records the query, the hits, and that none were citable. Removing the stage would hide the finding
and would also break the layer for the drilling-report side, where documents genuinely exist and
Agent B will need the same path.

**The investigation layer tops out at `supported_mechanism` on production episodes**, from the
structured channels alone. Five of fourteen reach it, four reach `proximate_driver`, and five reach
no level at all. The published figures say so in those words.

**No other document source is substituted to close the gap.** The corpus holds per-well engineering
documents and completion reports, and reaching for them here would be choosing a source after seeing
that the pre-registered one came up empty. Protocol section 15 already scopes retrieval to drilling
comments and those documents; widening the index is a protocol version with its own pushed commit,
and whether it helps is then a measurement rather than a hope.

## Consequences

The honest claim the layer can make about a production episode is narrower than the design
anticipated: it identifies what changed, from data, and says that no report explains why. That is the
output the handoff asked for in exactly those terms, and it turns out to be the only output the data
supports.

This is the third pre-registered capability this dataset has declined to support, after B1 drilling
plan reconstruction and C1 allocation reconciliation, and the three fail for one reason: the Volve
release is generous about measurements and thin about the operational record that explains them. A
reader should carry that into every conclusion here, and it is the single most useful thing this
project has learned about the dataset.

It also means a model-backed investigation role cannot be shown to beat `strongest-deviation` on
production episodes through better reading, because there is nothing to read. Where both named a
driver the two already agree on 5 of 6. Any future comparison has to be made on the drilling-report
layer, where the documents are, and protocol section 18.8's deferred pass marks should be fixed
against that layer rather than this one.
