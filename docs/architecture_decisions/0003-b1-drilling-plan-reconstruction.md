# ADR 0003: drilling plan reconstruction fails its feasibility criteria

Date: 2026-10-04
Status: accepted

## Context

`docs/eval_protocol.md` section 4 fixed, before any data was retrieved, what would count as
evidence that planned drilling durations can be reconstructed from auditable source data.
This records the result of running those criteria.

The prediction written into the protocol was that this would fail, on the reasoning that open
datasets rarely include the drilling programme. That reasoning turned out to be wrong. The
dataset contains eighteen drilling programme documents. The criteria still fail, for a
different reason, and the difference is worth stating because it changes what the result
means.

## Evidence

Twenty-six wells have daily drilling report coverage, so the required well count is
`max(1, min(3, ceil(26 / 2))) = 3`.

The structured route fails as the criteria anticipated. The reports carry `mdPlanned`, which
was null in all 220 sampled files, and which is a planned depth with no time dimension and so
excluded by condition 1 regardless. They also carry `forecast24Hr`, populated in 142 of 150
sampled, which condition 1 excludes by name as a rolling operational look-ahead rather than a
plan.

The documentary route produces four wells with a quotable planned duration: F-10 and F-15
carry section budget tables, F-5 a budget days table, and F-12 states a total budget time of
62.9 days against explicit start and finish datetimes. Fourteen other programme documents,
covering F-11, F-14, F-7 and F-9, state no planned duration at all.

Condition 3 then removes two of the four:

| well | drilling-reported days | days inside a stated plan | coverage |
|---|---:|---:|---:|
| F-10 | 59 | 59 | 100% |
| F-5 | 44 | 34 | 77% |
| F-15 | 137 | 57 | 42% |
| F-12 | 104 | 39 | 38% |

F-10 is a single contiguous campaign of 59 days from 7 April 2009, and its programme is dated
30 March 2009, so the plan covers all of it.

F-5 is three campaigns, not one: four days in November 2007, six in December 2007, and
thirty-four from 12 July to 20 August 2008. Its programme is dated 16 June 2008 and budgets
50.5 drilling days by section. That plan predates only the third campaign; condition 4 excludes
it from the two earlier ones, which it postdates. Coverage is therefore 34 of 44 days, which
still clears the 60% bar.

F-12's plan covers 7 June to 26 July 2007 while the well went on being drilled into 2008.
F-15's budget tables cover only its A and C sidetracks, which account for 57 of its 137 drilling
days; the programme for the main wellbore extracts as four characters of text, meaning it is a
scanned image, which condition 1 excludes because it cannot be quoted or audited.

Two wells satisfy every condition. Three are required.

## Decision

B1 fails. Recorded drilling time is reported in three categories, non-NPT recorded time, NPT,
and other unclassified time, and the interface states that planned durations cannot be
reconstructed from auditable source fields for these wells. No planning baseline is estimated,
inferred or back-computed. ADR 0002 records why the first category is not called productive
time.

## Consequences

The failure is on coverage, not availability, and that is a more useful finding than an
absence would have been. Plans exist; most of them describe one campaign of a well that was
drilled over several years, so a planned-versus-actual view built on them would compare a
decade of activity against a plan for its first two months and present the gap as overrun.

The verdict is not sensitive to a borderline call. F-12 and F-15 are far below the bar, so the
count is two whether F-5 is read generously or strictly, and one if F-5 were excluded
altogether.

Two wells do have complete plans. Nothing prevents a later version of this project from
reporting planned versus actual for F-10 and F-5 specifically, labelled as covering two wells
rather than the field. That would be a new decision with its own criteria, not a quiet
relaxation of this one.

Between 5% and 34% of drilling days, depending on the well, carry no hole size, which is the
field that makes section-boundary alignment possible. Any future section-based comparison has
to account for that gap rather than assume it away.
