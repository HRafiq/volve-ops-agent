# Operator console results: what it shows, what it refuses to show, and what building it found

Regenerate the checks with `python scripts/run_console_checks.py`. Exit status is the gate. No model
is called by any route.

Run it with `pip install -e ".[console]"`, then:

```
python -m uvicorn api.main:app --port 8000
```

The console is served by the same process as the API, at `/`. One process rather than a dev server
and a proxy, because the console is a read-only view of those payloads and splitting it across two
origins buys nothing but a CORS policy.

Protocol section 21 fixed all of this before any of it was built and was pushed as `prereg-v12`.
Amendment 9 corrected a claim section 21.5 made about the priority rule, and amendment 10 declared
mark 1's one exemption. Both are post-inspection and labelled as such.

## The rule the rest rests on

**The console renders. It does not compute.**

Every figure it shows is read from a run manifest or a per-episode artifact, carried by an object
that names where it came from. Where the console needed a figure no manifest held, the harness that
owns that figure was extended and the results table gained a row; the API never derived one and the
frontend does no arithmetic on a domain value beyond scaling it to a pixel.

That rule is not fastidiousness. A console that computes is a second implementation of the domain,
and this project has twice had to retract the word independent about one: section 14.3's integrity
walk and section 20.2's recorded-time walk both share code with the thing they check. A display that
recomputed a shortfall would be a third, with no gate on it and the widest audience.

**It forced three sets of figures into manifests**, and one of them is a result rather than
plumbing:

| figure | where it was | where it is now |
|---|---|---|
| Per-episode shortfall, duration, rates, gap fraction | computed inside the detector, discarded | `investigation.findings[]` |
| Six queue aggregates | nowhere | `investigation.*`, each with a table row |
| The selected model's **lower-tail rate** | inside a condition's detail string, unreadable | `expectation.lower_tail_rate` |

The last one matters. At the 7-day horizon it is **0.5632** against a section 8 band of 0.05 to 0.20,
so **56 percent of evaluated days fall below a bound that permits at most 20**. The expectation panel
shows that number where the band is drawn, because an operator reading a band has to know it does not
calibrate.

## The eight gating pass marks

| section 21.6 pass mark | result | what it examined |
|---|---|---|
| 1. Every payload figure resolves to a source | **pass** | 433 source strings across 16 payloads |
| 2. No mockup placeholder appears | **pass** | 72 figures extracted from the design mockup |
| 3. No hold-out well in any payload | **pass** | 16 rendered payloads, both spellings |
| 4. Abstention renders as its own state | **pass** | 4 findings that abstained, and only those |
| 5. Every money figure carries its assumption | **pass** | 1 money tile |
| 6. The review log is append-only | **pass** | 5 probes, each of which must be refused |
| 7. The API is read-only outside the review log | **pass** | 15 routes enumerated from the application |
| 8. The priority score equals the rule as printed | **pass** | 14 scores recomputed from the printed rule |

None examined nothing. Each is a function in `src/volve_ops/console/gates.py` with a test that makes
it fail, built by hand rather than from a passing run's artifacts, because a gate fed only those is
the shape five phases of this project reduced to.

Two of the eight are the last line rather than the only line, and that is deliberate. An unsourced
figure cannot be **constructed**: a numeric leaf in a payload is a typed object that requires a
source string. A currency amount cannot be constructed without its assumption. The gates catch what
the types cannot, which is a dict that bypassed the model or a tile built before the rule existed.

### Mark 2 cannot list what it checks against

Section 21.2 said the mockup's placeholder figures would be enumerated in the test suite. They are
not, and cannot be: the design mockup is a local-only file, and copying its contents into a tracked
file would publish private material to make a test convenient. The mark extracts them at check time
by shape, and reports examining **nothing** when the mockup is absent, so a skipped check is not
mistaken for a passed one. What stands in a clone without it is mark 1, which makes an invented
figure unconstructible rather than merely detectable.

### Mark 4 found a defect before anything else did

`15/9-F-14` from 2012-03-11 abstains with **nothing missing**. Every mandatory channel was available,
retrieval found no document, and no hypothesis reached the evidence threshold. The first version of
the abstention panel showed an empty "missing" list, which reads as the system saying there was no
reason it could not conclude.

The panel now renders the stop reason as its own line, which is a recorded field and not a new
figure. The other three abstentions are the opposite case, blocked on downhole pressure that is
absent for the whole episode.

## What the screen showed that no gate caught

Five defects, found by looking at the console rather than by running a check. Four of them are
strings, and mark 1 governs figures:

| what it showed | why |
|---|---|
| "? development producing wells" | a manifest key I guessed at and which does not exist |
| "naive-median28 (unknown)" | another one |
| "dataset unknown" | a third, where the freeze holds a rendered string rather than an object |
| "14.0" open investigations, "4.00" with no conclusion | the formatter chose decimals by magnitude, and JSON does not carry the int-float distinction |
| "protocol v12" while the document is at v14 | two different questions conflated, below |

The last is worth separating. A run manifest's `protocol_version` names the version whose **pass
marks** that layer implements. The investigation layer's are section 18.7's, unchanged since v4. I
had bumped that stamp to v12 when the harness started publishing figures for the console, which is a
different question entirely, and the header then told a reader the protocol document was at v12. The
stamp is back to v4 and the header shows the console's own.

**The sixth is the one worth reading.** The hypothesis matrix showed `H-water` as **Supported** with
every cell reading "Not applicable". It keyed evidence families off each hypothesis's
`required_channels`, which is empty for two of the five, so a supported conclusion displayed no
support at all. That is precisely the failure section 21.3 exists to prevent, arrived at from the
other direction: not a conclusion resting on nothing, but a conclusion whose evidence the screen hid.

Each hypothesis now fills the family it is actually judged on, carrying the strength feature that
decided it: the water-cut rise for `H-water`, the offset comparison against the other producing wells
for `H-field`. Both are figures section 18.2's bundle already computed and nothing was showing.

## What an operator can answer without leaving the page

The console design fixes eight questions. Where each is answered:

| question | where |
|---|---|
| What is the conclusion? | the assessment card, in operator words rather than schema values |
| What supports it? | the matrix, where every judged cell opens the object behind it |
| What contradicts it? | the same, in the contradicts state |
| What data is missing? | evidence coverage, with per-channel usable-day counts |
| Where did each number come from? | every figure carries its source; the drawer prints it in full |
| How was expected production calculated? | the expectation panel, including the interval that fails |
| What would change the conclusion? | the assessment card, from the finding's own field |
| Has a human reviewed it? | the review panel and its append-only log |

## Absence is an object

A cell reading "None found" is a recorded search with its own id, not a blank. It carries the corpus,
the filters, the queries issued and the count examined. Section 21.3's reasoning: a conclusion drawn
from nothing looks identical to one drawn from something unless the nothing is recorded, and a blank
cell is the most natural way to lose that distinction.

On this dataset every report cell is an absence except one. ADR 0008 records why: not one of 3,673
drilling-report events falls inside any episode window, because reports are written when a rig is on
the well and a producing well has no rig.

## The priority rule, and what it is worth

Printed under the queue with each row's own score, and with the count of episodes each term fired on.

| term | episodes it fires on |
|---|---:|
| cumulative shortfall | 14 of 14 |
| episode lasts 40 days or more | 5 of 14 |
| review is pending | **0 of 14** |
| no single explanation supported, in a high or moderate evidence band | 5 of 14 |

Producing 1 HIGH, 5 MEDIUM and 8 LOW.

The counts are published because the rubric flatters the rule. The review term fires on nothing until
someone uses the console. ADR 0009 records two further measurements: the choice between this clause
and a blunter one changes **no** episode's band on this data, so the dataset cannot tell them apart;
and removing the term altogether moves the single HIGH episode to MEDIUM and leaves the queue with no
HIGH case, so the term is the one thing in the rule that earns a promotion here.

**The queue header says the ordering is a stated convention and not a measured result.** Fourteen
episodes, one of them HIGH, cannot show that an ordering is a good ordering.

## No currency figure

The Estimated gross production value tile shows its reason instead of a number, because no oil price
assumption was supplied and none is built in. The type makes that the only possible rendering: an
amount and its assumption cannot be separated in the payload at all.

Section 20.3 fixed that rule for a document. A dashboard tile is the harder case, because a document
can carry its caveat in the next sentence and a tile has no next sentence.

## What is deferred

| not built | why | what would settle it |
|---|---|---|
| The Drilling and NPT workspace | section 21.8 gates Phase 6 on the Production workspace; the backend exists and `postmortem_results.md` carries every figure | rendering work, no new measurement |
| The System Health workspace | the same; `evaluation_results.md` carries every gate and figure | rendering work |
| Whether the priority rule orders the queue well | 14 episodes, 1 HIGH, and the disputed term changes no band | a dataset with review history, and episodes whose missing evidence is obtainable |
| Whether an operator can answer the eight questions | that is a usability result and needs operators | a session with people who do this work, which this project has no access to |
| Prose quality of a generated summary | no model is called, so there is no generated prose | section 19.8's rubric, and a model provider key |

The two planned workspaces show a page saying what they will hold rather than a dead tab or a screen
filled with illustrative numbers. Section 21.2 forbids the second outright.
