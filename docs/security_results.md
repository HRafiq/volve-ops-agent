# Phase 7 results: health, security and failure experiments

Pass marks in protocol section 22, written and pushed as `prereg-v16` before any of this ran.
Reproduce with `scripts/run_security_checks.py` and `scripts/run_ablations.py`.

## What "injection" means in a system with no model in it

The design brief lists seven prompt-injection invariants. Every one of them presumes document
text reaching a language model, and **no shipped module in this project calls one**. Three
therefore have nothing to hold against here, and this project's own standard forbids reporting a
vacuous check as a passed one.

| Section 11.3 invariant | Here |
|---|---|
| cannot override system/developer policy | vacuous: no prompt exists to override |
| system/developer prompts are not leaked | vacuous: there are none |
| cannot initiate tools merely because it instructs the model to | vacuous as written, replaced below |
| cannot broaden tool parameters | live |
| cannot access secrets or arbitrary local files | live |
| cannot alter the verdict or provenance schema | live |
| cannot disable grounding or human gating | live |

The third is replaced rather than dropped. Nothing here reads an instruction, but the stage
sequence is fixed and no document should be able to add a stage, a tool call or a retrieval
query. That is testable against the recorded trace.

Removing the model does not remove the attack surface; it moves it. What remains is data
injection against deterministic consumers, and the question becomes which consumers **interpret**
their input rather than recording it. Almost everything here records. The console interprets,
because a browser interprets markup, which makes the rendering layer the live channel in this
architecture and the one the brief does not mention. It is carried as an eighth invariant.

## The injection suite

38 payloads in six classes, through the real path a drilling report takes: parse, extract, index,
retrieve, investigate, compose, render.

| | |
|---|---:|
| held results recorded | 228 |
| of those, under the payload class written to attack that invariant | **71** |
| invariants violated | **0** |
| fixtures that never reached their consumer | **0** |
| invariants declared vacuous, not counted as preserved | 3 |
| live invariants never exercised | 0 |

Two held counts, not one. The suite runs most live invariants against every payload, so most held
results come from a class that was not written to provoke that invariant: a markup payload leaves
the stage sequence alone, and so would an empty document. Those observations are real and they are
not evidence that the invariant was tested. The gap between 228 and 71 is the useful part, and
publishing only the first would have been an inflated headline. `EXERCISED_BY` declared which
classes exercise which invariant and nothing consulted it until independent review asked.

### A fixture that never arrives has not been tested

Every phase of this project has found the same defect in a different costume: a check that could
not fail. Section 22.2 named the Phase 7 form of it in advance, which turned out to matter.

A hostile string in a field no parser reads passes every invariant while testing nothing. So each
fixture carries a reachability assertion, and the suite publishes three counts rather than one. A
run with anything in the third column has not finished.

It fired immediately. The first honest run reported the payload in **none** of the published
artifacts for every markup fixture. The cause is a real property of the system: the controller
quotes the first sentence carrying a term from its closed query map, so a payload appended as a
trailing sentence is never published at all.

**Only text the controller selects as a quote is ever published**, which makes the rendering
layer's exposure far narrower than a document's size suggests. The carrier now places the payload
where the selection will find it. The first version of the check called this a violation and
would have reported sixteen security failures that were nothing of the kind.

### What the browser does with it

Checked against the rendered DOM, not against the assembler. The console quotes **844 characters** of hostile text, inside an 884-character
blockquote whose first 39 characters are the episode's own benign span, with:

- zero child elements inside the quote, so nothing was parsed as markup;
- every marker in a text node, none in an attribute;
- no `javascript:` or `data:text/html` URL anywhere in the document;
- no `on*` event-handler attribute on any element;
- no script element but the application's own bundle;
- no window property set by any payload.

The console's one unescaped-markup sink was removed: a `dangerouslySetInnerHTML` rendering a
planned workspace title. It was fed two literals, reached no document text, and existed only to
turn an escaped ampersand into an ampersand. No payload could have exercised it, which is the
argument for the gate being a source check rather than a corpus check.

## Parsers and archives

21 attack fixtures, generated by a script so a reader can see what each contains. Every path they
name is under a directory that does not exist: a fixture pointing at `/etc/passwd` that succeeded
would look like a test that passed.

| | |
|---|---:|
| XML attack fixtures, all refused | 10 |
| archive attack fixtures, all refused | 11 |
| documents that must parse correctly | 1 |

Three fixtures were wrong, and what was wrong is worth more than the fixtures.

The **NFC collision** fixture used U+00F8, the o-slash, against an o with a combining diaeresis.
Those are different letters, they never collide, and the fixture asserted a refusal that correctly
never came.

The **compression-ratio** fixture was two megabytes, so the absolute per-member budget refused it
first and the ratio check never fired at all. Split into one fixture per bound, plus a third for
the archive total, which needed incompressible bytes: repeated characters compress about a
thousand to one, so the first attempt proved the ratio bound a third time.

The **encoding-mismatch** fixture is not an attack on this parser and now asserts that it parses
correctly. A re-encoding is a way past a filter that inspects content; `safe_xml` refuses
constructs and filters no content, so there is nothing to get past, and expat resolves the
encoding from the byte-order mark and returns the right text. A corpus holding only things that
must fail cannot tell a parser that refuses attacks from one that refuses everything.

## The API

The API had no automated tests at all before this phase, which is how a route taking a path
parameter came to be reasoned about rather than checked.

Enumerating **every** route that takes an investigation id, rather than the obvious ones, found
that `GET /api/investigations/{id}/review` consulted the review log alone and never the store. Any
string came back `200` with a state of `awaiting_review` and the string echoed as an investigation
id, so an episode that does not exist got a confident review panel. Never a traversal, since no
path was built from the id, but it is the failure the store names in its own message: an empty
screen looks like an answer.

Traversal is checked twice: by the status code, and by a CPython audit hook watching what the
process opened while refusing. A 404 says a lookup missed, not that no path was built. Across 8
routes and 8 traversal shapes, no file outside the store was opened and no denied path was
touched.

Bounds, fixed in section 22.8 before they were implemented: 4,000 characters for a review note,
200 for an actor name, 60 API requests per minute per client, 120 for static assets. A value over
a bound is refused with the limit in the error rather than truncated, because the review log is
append-only and a shortened correction is a falsified record.

The rate limiter's own limits are stated in its module and are real: one process, keyed by peer
address with `X-Forwarded-For` deliberately not trusted, and a fixed window that admits a burst at
the boundary. It stops a loop; it is not traffic shaping.

## Provenance failures

Seven classes, each built as something the type system accepts and handed to the real publication
gate. A test that builds an invalid finding and asserts the constructor refused it has tested the
constructor.

Six are investigation-gate classes and the gate blocks all six. Class 3 is not a gate class at
all: a `Finding` carries fact ids and no figures, so nothing in it can contradict a record. The
figures are in the console payloads, which is where amendment 11 found 198 of 198 drawer figures
attributed to facts recording different numbers, every source resolving, every check passing.
Resolving is weaker than supporting, and mark 1 asks the weaker question by design.

**Figures contradicting their records: 0.**

The first run of that check reported 183. Every one was false. Fact ids restart at `fact_000001`
for every episode, so a single map across the cache compares one episode's figure with another
episode's record. This is the third time in this project a verification script has produced a
false finding by indexing one thing against another, so the fix is not only the scoping: the safe
entry point does the scoping itself, and the trap is pinned as a test.

## Ablations

Development data only. The hold-out is untouched.

### Expectation

| model | episodes opened | WAPE |
|---|---:|---:|
| naive-median28 *(selected)* | 14 | 0.1211 |
| naive-persistence | 12 | 0.1216 |
| exponential-decline | 11 | 0.1200 |
| hyperbolic-decline | 11 | 0.1199 |
| choke-scaled | **18** | **0.0984** |

**Accuracy and investigation volume move in opposite directions here.** `choke-scaled` is the most
accurate of the five by about 19 percent and opens the most episodes; the two decline models open
the fewest. That is the measurement a WAPE table cannot make: a model that expects too much
manufactures work for a human to read. It does not by itself say `choke-scaled` is wrong, because
these are opened episodes and not confirmed false positives, and nothing here establishes which of
the 18 are real.

### Retrieval

Two of fourteen development episodes have any in-window document, which ADR 0008 predicted. An
ablation over two episodes measures two episodes, and the population is published with the result
rather than left for a reader to find.

The population was published as **one** until independent review found it. The harness skipped an
episode when the with-documents arm cited no span, under a comment saying the episode had no
document to take away. Those are different claims, and the second of the two episodes has four
in-window documents and cites none of them. Amendment 12 records it. On that episode nothing moves,
which mark 9 requires be reported rather than dropped: it is `insufficient_evidence` with and
without, and removing documents it could not cite changes nothing.

On the first, 15/9-F-14 from 2012-01-31, removing the document:

| | with the document | without |
|---|---|---|
| verdict | supported_explanation | supported_explanation |
| evidence band | high | high |
| **causal level** | **documented_root_cause** | **proximate_driver** |

The causal level is what moves, which is exactly what the retrieval stage exists to lift. A first
version of this script printed the verdict alone and the run read as a null result.

### Calibration

| | |
|---|---|
| evidence-derived bands over 14 findings | 7 high, 5 moderate, 2 low |
| flat prior at the corpus mean 0.653 | all 14 in moderate |
| evidence-derived score spread | 0.580 |

A flat prior places every finding in one band by construction, so what this measures is whether the
evidence score carries information, not whether it is well calibrated. **There is no ground truth
here for whether a band was right**, and four of the five features are derived from inputs to the
verdict, which bounds what the spread is worth.

A first version declined this ablation as not applicable, on the grounds that there is no raw model
self-report to compare against. Section 22.7.3 never asked for one: it pre-registered the
evidence-derived score against a flat prior, which was implementable throughout. Amendment 12
records it.

### Cost and latency

Wall-clock figures are not quoted here. They are regenerated by every run and a fixed sentence in a
document is guaranteed to drift from the artifact; the first version of this section quoted 0.26 ms
and 1.89 ms against a manifest recording 0.20 and 1.57. The System Health workspace renders them
from `ablation_run.json`, which is where they belong.

What is stable and worth stating: the controller's own time is roughly an order of magnitude below
the end-to-end time, and at fourteen samples the 95th-percentile order statistic is the maximum.

Two timers, not one. The controller runs over a bundle that is already built, and building it is
what touches the production history, so a controller-only figure is one no caller could observe.
Neither includes loading the workbook.

Token and model-call cost is **declared not applicable** rather than reported as zero. No module
calls a model, so a cost curve denominated in tokens would be decorative.

## The System Health workspace

Every figure on it is read from `security_run.json` or `ablation_run.json`, and every one of them
resolves under the same mark 1 gate every other screen's figures go through. **Mark 1 asks whether a
source resolves, which for a manifest path means only that the key exists**, so class 3 now asks the
stronger question of this screen too: whether the figure equals the value at that key. The count of
sources the gate examined is in `security_run.json`, which is where it belongs: it changes
whenever a row is added, and a figure fixed in a sentence drifts from the artifact. A first
version of this paragraph quoted 28 against 35 examined, and the correction replaced it with a
claim that the count was on the screen, which it is not. Section 21.1 holds
here as everywhere: it renders and does not compute, **including its deltas**.

The version comparison prints a reason where a delta would go, because only one scored version
exists. A `0.00` against an absent baseline is a figure from nowhere, and an empty column reads as
no change, which is the most likely way this screen would lie. `ComparisonRow` cannot be
constructed without either a previous value or a stated reason.

The three vacuous invariants are a separate block with their reasons, never a row in the counts. A
screen that listed them beside the tested ones would undo in the display what the report structure
exists to prevent.

## Overclaims

A gate over 132 files finds 0. It matches claim shapes rather than the bare phrase, because the
protocol section forbidding the claim contains the words. Like the sink gate it has no exception
list, so the project's prose has to be written around it: the first run flagged a sentence in the
gate's own docstring, which was reworded rather than excepted.

Section 11.1 is the standard being held to. The read-only posture reduces the operational risk
surface and preserves human decision authority. It is not a formal offshore safety case, which is
a far broader thing involving hazard identification, safety-critical elements and a regulator, and
nothing in this project should be read as claiming otherwise.

## What this phase does not show

- **Most of the injection brief stays untested**, because the component it is written for does not
  exist here. Three invariants are vacuous and are reported that way. They become live the moment a
  model-backed stage is added.
- **The retrieval ablation is two episodes**, one of which moves nothing. It demonstrates that the
  measurement works; it is not evidence about retrieval in general.
- **The rate limiter is per process** and keyed by peer address. Behind a proxy every client shares
  one bucket.
- **Correction-store leakage** (F11) is still vacuous: the store is empty, so section 19.2's fourth
  check has nothing to test.
- **The version comparison has one version.** Mark 12 keeps it honest; it does not make it useful.
- **The rendered-DOM check is a browser experiment, not a CI step.** Mark 2's source gate runs on
  every push and is what stands in CI; mark 3 reproduces from
  `scripts/serve_injected_console.py` and `scripts/check_rendered_inert.js`.
