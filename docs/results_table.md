### Data and split

| metric | value | denominator | status | what would settle it |
|---|---|---|---|---|
| Drilling reports read | 1759 | WITSML drill reports in the share | `reported` | — |
| Leakage audit, five checks of section 19.2 | pass | computed by the harness, not a manifest | `gated` | — |

### Expectation engine

| metric | value | denominator | status | what would settle it |
|---|---|---|---|---|
| Episodes opened on development data | 14 | development days of 6 producing wells | `reported` | — |
| Days evaluated, naive-median28 | 2548 | development valid producing days with a fitted window | `reported` | — |
| Days evaluated, naive-persistence | 2548 | development valid producing days with a fitted window | `reported` | — |
| Days evaluated, exponential-decline | 2548 | development valid producing days with a fitted window | `reported` | — |
| Days evaluated, hyperbolic-decline | 2548 | development valid producing days with a fitted window | `reported` | — |
| Days evaluated, choke-scaled | 2548 | development valid producing days with a fitted window | `reported` | — |
| Interval coverage within the section 8 band | deferred | development valid producing days, 2 wells reaching the 150-day gate | `deferred` | an interval construction that calibrates; the current one fails by 2 to 4 times and the failure is reported in docs/expectation_results.md |
| Episode precision and recall | deferred | would need a curated episode set | `deferred` | a curated episode set; section 19.11 declines to manufacture one from 14 episodes on 2 wells |

### Drilling-report extraction

| metric | value | denominator | status | what would settle it |
|---|---|---|---|---|
| Non-productive events extracted | 3673 | 23,447 activity blocks | `reported` | — |
| Narrative chunks indexed | 3673 | one per extracted event comment | `reported` | — |
| Section 14.3 event detection is exact | pass | 617 qualifying blocks in the labelled sample's 99 documents | `gated` | — |
| Section 14.3 duration is exact | pass | 617 qualifying blocks, to within one minute | `gated` | — |
| Qualifying blocks checked | 617 | blocks meeting the section 14.1 rule in those documents | `reported` | — |
| Events checked against the source | 617 | as above; equality with it is the detection pass mark | `reported` | — |
| Documents walked independently of the extractor | 99 | source documents of the labelled sample | `reported` | — |

### Cause labels

| metric | value | denominator | status | what would settle it |
|---|---|---|---|---|
| Labels in the development set | 135 | the section 16 stratified draw, target 120 to 150 | `reported` | — |
| Expert labels | 0 | of the 135; the rest are machine-assisted per section 17 | `reported` | — |
| Selection permitted by section 17.2 | FAIL | false while any label is machine-assisted | `gated` | — |
| Events with a stated cause | 60 | 135 labelled events | `reported` | — |
| Spans cited, all verbatim | 60 | one per attributed label; verbatim checked on every read | `gated` | — |
| Rows carrying a note | 55 | 135 labelled events | `reported` | — |
| Notes naming a rejected alternative label | 14 | the 55 rows carrying a note | `reported` | — |
| echo-subcategory macro-F1 | 0.2992 | 5 classes clearing the 5-instance floor, of 135 events | `reported` | — |
| echo-statedetail macro-F1 | 0.3329 | 5 classes clearing the 5-instance floor, of 135 events | `reported` | — |
| echo-subcategory exact agreement | 0.2963 | 135 labelled events | `reported` | — |
| echo-statedetail exact agreement | 0.5481 | 135 labelled events | `reported` | — |
| echo-subcategory classes in the macro average | 5 | of 12 taxonomy classes; 2 are unreachable per the guide | `reported` | — |
| echo-statedetail classes in the macro average | 5 | of 12 taxonomy classes; 2 are unreachable per the guide | `reported` | — |
| The two baselines agree with each other | 0.4444 | 135 labelled events | `reported` | — |
| Labels match the baselines' consensus | 0.4167 | the 60 events where both baselines agree | `reported` | — |
| Consensus is `not_stated` | 44 | the 60 events where both baselines agree | `reported` | — |
| Of those, labels name a cause | 20 | the 44 where the consensus abstains | `reported` | — |
| Consensus names a cause | 16 | the 60 events where both baselines agree | `reported` | — |
| Of those, labels agree | 1 | the 16 where the consensus names a cause | `reported` | — |
| Source coding flagged as disagreeing with the comment | 21 | 135 labelled events; judgement-based, criterion in the guide | `reported` | — |
| Source coding disagreement rate | 0.1556 | as above | `reported` | — |
| Subcategory names a cause that is not the label | 0.4963 | 135 labelled events; the mechanical companion, needing no judgement | `reported` | — |
| Cause attribution macro-F1 against a selected approach | deferred | would need expert labels | `deferred` | an adjudication by a reader with drilling-operations experience, per protocol section 17.4, at 80 percent agreement on the 40 drawn events |
| Inter-pass label agreement | deferred | withdrawn | `deferred` | nothing; protocol amendment 2 withdrew it, because re-running a model over the same comments does not estimate a person's consistency with themselves |

### Retrieval

| metric | value | denominator | status | what would settle it |
|---|---|---|---|---|
| Chunks in the index at investigation time | 3673 | one per extracted event comment | `reported` | — |
| Evidence window either side of an episode | 45 | days; post-inspection per amendment 4, and outcome-determining | `reported` | — |
| Recall at k against a gold evidence set | deferred | would need a gold evidence set | `deferred` | the curated episode set section 15 defers, and a gold evidence set built from it; neither exists and section 15 declines to fix a threshold against either |

### Investigation

| metric | value | denominator | status | what would settle it |
|---|---|---|---|---|
| Episodes investigated | 14 | all development episodes from the section 9 detector | `reported` | — |
| All five section 18.7 gates pass | pass | 14 findings | `gated` | — |
| Document citations | 2 | across all 14 findings | `reported` | — |
| Findings reaching `documented_root_cause` | 1 | 14 findings | `reported` | — |
| Agreement with `strongest-deviation` on the driver family | 5 | the episodes where both named a driver | `reported` | — |
| Episodes where both named a driver | 7 | 14 episodes; the baseline abstains on 7 | `reported` | — |
| False root-cause claims, mechanical half | 0 | findings claiming a documented root cause; computed by the harness | `gated` | — |
| False root-cause rate, the half needing a reader | deferred | would need correctness | `deferred` | an adjudication by a reader with drilling-operations experience, per protocol section 17.4; section 19.5 fixes the 5-to-1 weighting against an abstention now |
| Hypothesis-set precision, recall and F1 | deferred | would need gold hypothesis sets | `deferred` | an adjudication by a reader with drilling-operations experience, per protocol section 17.4 |
| Risk and coverage curve | deferred | would need correctness | `deferred` | correctness per above; section 19.6 fixes both axes and notes that three evidence bands give three points, which is a curve only by courtesy |
| Calibrated confidence | deferred | 14 episodes | `deferred` | more episodes and an outcome definition; at 14, a per-bin interval is about 25 points wide, so section 19.4 reports evidence bands and no outcome rates |
| Prose-quality judge scores | deferred | would need a model and the author's own scores | `deferred` | a configured model provider key; the rubric is fixed in section 19.8, and prose quality is the one thing here the author can judge unaided |
