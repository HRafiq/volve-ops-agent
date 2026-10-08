### Data and split

| metric | value | denominator | status | what would settle it | note |
|---|---|---|---|---|---|
| Drilling reports read | 1759 | WITSML drill reports in the share | `reported` | - | - |
| Leakage audit, five checks of section 19.2 | pass | computed by the harness, not a manifest | `gated` | - | reported in the harness output rather than a run manifest |

### Expectation engine

| metric | value | denominator | status | what would settle it | note |
|---|---|---|---|---|---|
| Episodes opened on development data | 14 | development days of 5 producing wells | `reported` | - | one detector, two wells carry all of them; not a benchmark, per section 19.11 |
| Days evaluated, naive-median28 | 2548 | development valid producing days with a fitted window | `reported` | - | - |
| Days evaluated, naive-persistence | 2548 | development valid producing days with a fitted window | `reported` | - | - |
| Days evaluated, exponential-decline | 2548 | development valid producing days with a fitted window | `reported` | - | - |
| Days evaluated, hyperbolic-decline | 2548 | development valid producing days with a fitted window | `reported` | - | - |
| Days evaluated, choke-scaled | 2548 | development valid producing days with a fitted window | `reported` | - | - |
| Interval coverage within the section 8 band | deferred | development valid producing days, 2 wells reaching the 150-day gate | `deferred` | an interval construction that calibrates; the current one fails by 2 to 4 times and the failure is reported in docs/expectation_results.md | - |
| Episode precision and recall | deferred | would need a curated episode set | `deferred` | a curated episode set; section 19.11 declines to manufacture one from 14 episodes on 2 wells | - |

### Drilling-report extraction

| metric | value | denominator | status | what would settle it | note |
|---|---|---|---|---|---|
| Non-productive events extracted | 3673 | 23,447 activity blocks | `reported` | - | - |
| Narrative chunks indexed | 3673 | one per extracted event comment | `reported` | - | - |
| Section 14.3 event detection is exact | pass | 617 qualifying blocks in the labelled sample's 99 documents | `gated` | - | - |
| Section 14.3 duration is exact | pass | 617 qualifying blocks, to within one minute | `gated` | - | - |
| Qualifying blocks checked | 617 | blocks meeting the section 14.1 rule in those documents | `reported` | - | - |
| Events checked against the source | 617 | as above; equality with it is the detection pass mark | `reported` | - | - |
| Documents walked by the section 14.3 second path | 99 | source documents of the labelled sample | `reported` | - | - |

### Cause labels

| metric | value | denominator | status | what would settle it | note |
|---|---|---|---|---|---|
| Labels in the development set | 135 | the section 16 stratified draw, target 120 to 150 | `reported` | - | - |
| Expert labels | 0 | of the 135; the rest are machine-assisted per section 17 | `reported` | - | zero, which is what suspends the section 14.5 selection gate |
| Selection permitted by section 17.2 | FAIL | false while any label is machine-assisted | `gated` | - | gated in the sense that the code refuses selection, not that false is a failure |
| Events with a stated cause | 60 | 135 labelled events | `reported` | - | - |
| Spans cited, all verbatim | 60 | one per attributed label; verbatim checked on every read | `gated` | - | - |
| Rows carrying a note | 55 | 135 labelled events | `reported` | - | - |
| Notes naming a rejected alternative label | 14 | the 55 rows carrying a note | `reported` | - | - |
| echo-subcategory macro-F1 | 0.2992 | 5 classes clearing the 5-instance floor, of 135 events | `reported` | - | reported, not gated: section 17.2 suspends the selection gate |
| echo-statedetail macro-F1 | 0.3329 | 5 classes clearing the 5-instance floor, of 135 events | `reported` | - | reported, not gated: section 17.2 suspends the selection gate |
| echo-subcategory exact agreement | 0.2963 | 135 labelled events | `reported` | - | - |
| echo-statedetail exact agreement | 0.5481 | 135 labelled events | `reported` | - | - |
| echo-subcategory classes in the macro average | 5 | of 12 taxonomy classes; 2 are unreachable per the guide | `reported` | - | - |
| echo-statedetail classes in the macro average | 5 | of 12 taxonomy classes; 2 are unreachable per the guide | `reported` | - | - |
| The two baselines agree with each other | 0.4444 | 135 labelled events | `reported` | - | - |
| Labels match the baselines' consensus | 0.4167 | the 60 events where both baselines agree | `reported` | - | - |
| Consensus is `not_stated` | 44 | the 60 events where both baselines agree | `reported` | - | - |
| Of those, labels name a cause | 20 | the 44 where the consensus abstains | `reported` | - | - |
| Consensus names a cause | 16 | the 60 events where both baselines agree | `reported` | - | - |
| Of those, labels agree | 1 | the 16 where the consensus names a cause | `reported` | - | one of sixteen; unresolved and published as unresolved |
| Source coding flagged as disagreeing with the comment | 21 | 135 labelled events; judgement-based, criterion in the guide | `reported` | - | - |
| Source coding disagreement rate | 0.1556 | as above | `reported` | - | - |
| Subcategory names a cause that is not the label | 0.4963 | 135 labelled events; the mechanical companion, needing no judgement | `reported` | - | - |
| Cause attribution macro-F1 against a selected approach | deferred | would need expert labels | `deferred` | an adjudication by a reader with drilling-operations experience, per protocol section 17.4, at 80 percent agreement on the 40 drawn events | - |
| Inter-pass label agreement | deferred | withdrawn | `deferred` | nothing; protocol amendment 2 withdrew it, because re-running a model over the same comments does not estimate a person's consistency with themselves | - |

### Retrieval

| metric | value | denominator | status | what would settle it | note |
|---|---|---|---|---|---|
| Chunks in the index at investigation time | 3673 | one per extracted event comment | `reported` | - | - |
| Evidence window either side of an episode | 45 | days; post-inspection per amendment 4, and outcome-determining | `reported` | - | - |
| Recall at k against a gold evidence set | deferred | would need a gold evidence set | `deferred` | the curated episode set section 15 defers, and a gold evidence set built from it; neither exists and section 15 declines to fix a threshold against either | - |

### Investigation

| metric | value | denominator | status | what would settle it | note |
|---|---|---|---|---|---|
| Episodes investigated | 14 | all development episodes from the section 9 detector | `reported` | - | - |
| All five section 18.7 gates pass | pass | 14 findings | `gated` | - | two of the five have little on this corpus to examine; docs/investigation_results.md says which |
| Document citations | 2 | across all 14 findings | `reported` | - | - |
| Findings reaching `documented_root_cause` | 1 | 14 findings | `reported` | - | one; ADR 0008 records why it is rare rather than impossible |
| Agreement with `strongest-deviation` on the driver family | 5 | the episodes where both named a driver | `reported` | - | the two share most of their implementation, so this largely measures shared code |
| Episodes where both named a driver | 7 | 14 episodes; the baseline abstains on 7 | `reported` | - | - |
| False root-cause claims, mechanical half | 0 | findings claiming a documented root cause; computed by the harness | `gated` | - | - |
| False root-cause rate, the half needing a reader | deferred | would need correctness | `deferred` | an adjudication by a reader with drilling-operations experience, per protocol section 17.4; section 19.5 fixes the 5-to-1 weighting against an abstention now | - |
| Hypothesis-set precision, recall and F1 | deferred | would need gold hypothesis sets | `deferred` | an adjudication by a reader with drilling-operations experience, per protocol section 17.4 | - |
| Risk and coverage curve | deferred | would need correctness | `deferred` | correctness per above; section 19.6 fixes both axes and notes that three evidence bands give three points, which is a curve only by courtesy | - |
| Calibrated confidence | deferred | 14 episodes | `deferred` | more episodes and an outcome definition; at 14, a per-bin interval is about 25 points wide, so section 19.4 reports evidence bands and no outcome rates | - |
| Prose-quality judge scores | deferred | would need a model and the author's own scores | `deferred` | a configured model provider key; the rubric is fixed in section 19.8, and prose quality is the one thing here the author can judge unaided | - |

### Expectation engine

| metric | value | denominator | status | what would settle it | note |
|---|---|---|---|---|---|
| WAPE, naive-median28, horizon 7 | 0.1211 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, naive-median28, horizon 14 | 0.1233 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, naive-median28, horizon 28 | 0.1297 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, naive-persistence, horizon 7 | 0.1216 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, naive-persistence, horizon 14 | 0.1236 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, naive-persistence, horizon 28 | 0.1338 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, exponential-decline, horizon 7 | 0.12 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, exponential-decline, horizon 14 | 0.124 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, exponential-decline, horizon 28 | 0.1367 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, hyperbolic-decline, horizon 7 | 0.1199 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, hyperbolic-decline, horizon 14 | 0.1239 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, hyperbolic-decline, horizon 28 | 0.1364 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, choke-scaled, horizon 7 | 0.0984 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, choke-scaled, horizon 14 | 0.109 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |
| WAPE, choke-scaled, horizon 28 | 0.1321 | development valid producing days at that horizon | `reported` | - | section 4's selection rule is defined in these; none clears section 8's bar |

### Drilling-report extraction

| metric | value | denominator | status | what would settle it | note |
|---|---|---|---|---|---|
| Labelling sample, development, target | 135 | non-productive events eligible under section 16 | `reported` | - | - |
| Labelling sample, development, drawn | 135 | non-productive events eligible under section 16 | `reported` | - | - |
| Labelling sample, development, eligible | 2538 | non-productive events eligible under section 16 | `reported` | - | - |
| Labelling sample, hold-out, target | 60 | non-productive events eligible under section 16 | `reported` | - | - |
| Labelling sample, hold-out, drawn | 60 | non-productive events eligible under section 16 | `reported` | - | - |
| Labelling sample, hold-out, eligible | 616 | non-productive events eligible under section 16 | `reported` | - | - |

### Cause labels

| metric | value | denominator | status | what would settle it | note |
|---|---|---|---|---|---|
| Labels assigned `not_stated` | 75 | 135 labelled events | `reported` | - | - |
| Labels assigned `equipment_failure` | 25 | 135 labelled events | `reported` | - | - |
| Labels assigned `hole_problem` | 14 | 135 labelled events | `reported` | - | - |
| Labels assigned `waiting_on_weather` | 8 | 135 labelled events | `reported` | - | - |
| Labels assigned `other` | 5 | 135 labelled events | `reported` | - | - |
| Labels assigned `waiting_on_cement` | 3 | 135 labelled events | `reported` | - | - |
| Labels assigned `waiting_on_logistics` | 2 | 135 labelled events | `reported` | - | - |
| Labels assigned `well_control` | 2 | 135 labelled events | `reported` | - | - |
| Labels assigned `human_or_procedural` | 1 | 135 labelled events | `reported` | - | - |
| Labels assigned `equipment_maintenance` | 0 | 135 labelled events | `reported` | - | - |
| Labels assigned `rig_service` | 0 | 135 labelled events | `reported` | - | - |
| Labels assigned `cementing_problem` | 0 | 135 labelled events | `reported` | - | - |
| Labels settled by rule `P1` | 46 | 135 labelled events | `reported` | - | - |
| Labels settled by rule `taxonomy` | 34 | 135 labelled events | `reported` | - | - |
| Labels settled by rule `P2` | 22 | 135 labelled events | `reported` | - | - |
| Labels settled by rule `P1-unreachable` | 10 | 135 labelled events | `reported` | - | - |
| Labels settled by rule `P1-span` | 7 | 135 labelled events | `reported` | - | - |
| Labels settled by rule `P1-monitor` | 4 | 135 labelled events | `reported` | - | - |
| Labels settled by rule `P1-outcome` | 4 | 135 labelled events | `reported` | - | - |
| Labels settled by rule `P1-total` | 3 | 135 labelled events | `reported` | - | - |
| Labels settled by rule `P2-test` | 3 | 135 labelled events | `reported` | - | - |
| Labels settled by rule `L2-ambiguous` | 1 | 135 labelled events | `reported` | - | - |
| Labels settled by rule `L4` | 1 | 135 labelled events | `reported` | - | - |

### Investigation

| metric | value | denominator | status | what would settle it | note |
|---|---|---|---|---|---|
| Findings with verdict `supported_explanation` | 7 | 14 episodes | `reported` | - | - |
| Findings with verdict `multiple_plausible_explanations` | 3 | 14 episodes | `reported` | - | - |
| Findings with verdict `insufficient_evidence` | 4 | 14 episodes | `reported` | - | - |
| Findings stopping on `evidence_threshold_met` | 4 | 14 episodes | `reported` | - | - |
| Findings stopping on `evidence_exhausted` | 7 | 14 episodes | `reported` | - | - |
| Findings stopping on `mandatory_evidence_unavailable` | 3 | 14 episodes | `reported` | - | - |
| Findings stopping on `step_budget_reached` | 0 | 14 episodes | `reported` | - | - |
| Findings stopping on `cost_budget_reached` | 0 | 14 episodes | `reported` | - | - |
| Findings reaching level `proximate_driver` | 3 | 14 episodes | `reported` | - | - |
| Findings reaching level `supported_mechanism` | 5 | 14 episodes | `reported` | - | - |
| Findings reaching level `documented_root_cause` | 1 | 14 episodes | `reported` | - | - |
| Findings reaching level `None` | 5 | 14 episodes | `reported` | - | - |
| Section 18.7 gate: provenance validity is 100 percent | pass | 14 findings | `gated` | - | - |
| Section 18.7 gate: stop-condition honesty is 100 percent | pass | 14 findings | `gated` | - | - |
| Section 18.7 gate: trace replay is exact | pass | 14 findings | `gated` | - | - |
| Section 18.7 gate: abstention is reachable and used | pass | 14 findings | `gated` | - | - |
| Section 18.7 gate: no forbidden root-cause wording | pass | 14 findings | `gated` | - | - |

### Post-mortem

| metric | value | denominator | status | what would settle it | note |
|---|---|---|---|---|---|
| Activity blocks walked | 23447 | every block in 1,759 drilling reports | `reported` | - | - |
| Reports walked | 1759 | WITSML drill reports in the corpus | `reported` | - | - |
| Untimed blocks | 0 | 23,447 activity blocks | `reported` | - | zero; a qualifying block that cannot be timed is a parser defect under section 14.3 |
| Corpus non-productive time | 8563.25 | all 11 wells, hours | `reported` | - | - |
| Corpus non-NPT recorded time | 30834.73 | all 11 wells, hours | `reported` | - | ADR 0002: not called productive |
| Corpus other unclassified time | 97.5 | all 11 wells, hours | `reported` | - | gaps between blocks inside a report; the third ADR 0002 category |
| Corpus concurrent block overlap | 1.75 | all 11 wells, hours | `reported` | - | reported separately, never folded into the reconciliation tolerance |
| Development non-productive time | 7430.25 | 7 development wells, hours | `reported` | - | - |
| Development non-NPT recorded time | 24894.23 | 7 development wells, hours | `reported` | - | - |
| Share of corpus NPT hours held out and not reported | 0.1323 | corpus non-productive hours | `reported` | - | section 20.1 confines the post-mortem to development wells |
| Recurring patterns in the register | 13 | patterns clearing 3 wells and 24 hours | `reported` | - | - |
| Patterns below the section 20.4 thresholds | 38 | distinct subcategory and detail-state pairs | `reported` | - | - |
| Hours in patterns below the thresholds | 1199.75 | development non-productive hours | `reported` | - | - |
| Hours in recurring patterns | 6230.5 | development non-productive hours | `reported` | - | - |
| Register coverage of development NPT hours | 0.8385 | development non-productive hours | `reported` | - | reported, never gated: how concentrated a corpus is, is a property of the data |
| Rig day rate assumed | not requested | USD per day, supplied on the command line or absent | `reported` | - | absent on every run so far; section 20.3 refuses a figure without its assumption |
| Estimated rig-time cost equivalent | not requested | development non-productive hours at the assumed rate | `reported` | - | an illustration, never a finding; the assumption travels with the number |
| Corrections in the store | 0 | across every store version | `reported` | - | zero; a correction needs a person, so section 19.2's fourth check is still vacuous |
| All 7 section 20.6 gates pass | pass | the post-mortem, the register and the correction store | `gated` | - | - |
| Section 20.6 gate: 20.6 the corpus is not empty | pass | the post-mortem run | `gated` | - | - |
| Section 20.6 gate: 20.2 categories reconcile and the store agrees on hours and counts | pass | the post-mortem run | `gated` | - | - |
| Section 20.6 gate: 20.6 every citation resolves | pass | the post-mortem run | `gated` | - | - |
| Section 20.6 gate: 20.6 no hold-out well in the post-mortem, the register or the store | pass | the post-mortem run | `gated` | - | - |
| Section 20.6 gate: 20.3 no currency figure without a sound, disclosed assumption | pass | the post-mortem run | `gated` | - | - |
| Section 20.6 gate: 20.5 a hold-out correction is refused at write time | pass | the post-mortem run | `gated` | - | - |
| Section 20.6 gate: 20.6 the register is reproducible | pass | the post-mortem run | `gated` | - | - |
| Planned versus actual drilling time | deferred | would need drilling programmes covering 3 wells | `deferred` | programmes this dataset does not contain; ADR 0003 records the failure and section 20.2's three categories are the substitute | - |
| Whether a recurring pattern is a correct lesson | deferred | would need correctness | `deferred` | an adjudication by a reader with drilling-operations experience, per protocol section 17.4, extended to the register's entries | - |
| Effect of the correction loop on extraction quality | deferred | would need corrections and a second extraction version | `deferred` | corrections from a person, then a second extraction version scored against the first with section 20.5's leakage rule observed | - |
| Events in recurring patterns | 2600 | non-productive events on development wells | `reported` | - | - |
| Of those, events carrying a cause label | 65 | events in recurring patterns | `reported` | - | - |
| Labelled fraction of recurring patterns | 0.025 | events in recurring patterns | `reported` | - | the phase's headline figure; review found it quoted in bold and computable from neither the manifest nor the harness output |
| Largest pattern the thresholds exclude | 561.5 | hours, on a single well | `reported` | - | a single-well event cannot enter the register however expensive; the register publishes what it excludes |
