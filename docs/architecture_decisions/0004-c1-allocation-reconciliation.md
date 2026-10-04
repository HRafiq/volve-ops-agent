# ADR 0004: allocation reconciliation cannot be reconstructed from this dataset

Date: 2026-10-04
Status: accepted

## Context

`docs/eval_protocol.md` section 5 fixed, before any data was retrieved, what would count as
evidence that an independent aggregate production series exists and can be compared honestly
against the sum of per-well allocated volumes. This records the result.

## Evidence

The production workbook holds two sheets, daily and monthly. Both are per-wellbore and both
cover the same seven wellbores. Neither carries a field total, a facility total, or any row
that is not attributed to a single wellbore. There is no export meter series, no fiscal or
sales meter series, and no lifting record anywhere in the production data.

The only other process data in the share is a PI System folder of sensor tags for Sleipner,
which is a different field. It is not a Volve export series and cannot stand in for one.

Public regulatory figures for field-level production were admitted into scope by condition 1,
which is why the protocol named them. They do not rescue the gate. Such figures are
operator-reported and derived from the same allocation as the per-well volumes, so condition 1
is not satisfied, and they carry no documented metered-versus-allocated basis, so condition 2
is not satisfied either. The protocol predicted this specific failure mode and it holds.

## Decision

C1 fails. An allocation reconciliation capability is not built, and the reason is documented
here rather than left as an unexplained gap in scope.

## Consequences

The feasibility finding is the engineering outcome. A reconciliation needs two independently
derived measurements of the same quantity, and this dataset contains one measurement expressed
at two levels of aggregation. Building something on top of that would produce a number that
looks like a reconciliation and is actually an identity.

This was already the weaker of the two optional directions and it was deferred behind the core
capabilities regardless, so nothing downstream changes.
