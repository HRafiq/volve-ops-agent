"""The leakage audit of protocol section 19.2.

The Phase 4 gate is "dev results table; hold-out untouched". Untouched is a claim, and a claim about
one's own discipline is the kind most worth checking mechanically, because the failure mode is not
dishonesty but forgetting: a filter applied one call too late, a well that looks like a development
well because it never appears in the output.

Five checks, all gating. A failure is an incident rather than a score: the affected result is
withdrawn, not reported with a caveat.

**The defect independent review found here, recorded because it is the whole lesson.** Check 3 tests
whether a fitted day falls outside the development window. Its first version was handed a day set
the harness had computed itself with `development_only`, so the check tested the negation of the
comprehension that had produced its own input. It could not fail, and the reviewer demonstrated it
by changing the expectation study to fit on the whole record, including 3,201 hold-out producing
days: the audit reported clean and every pass mark passed.

A check cannot audit another script's filtering by re-deriving it. So the scripts now record the
dates they actually fitted and swept on, in their own run manifests, and this module tests those.
That is the difference between auditing a run and re-performing it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.domain.splits import TemporalSplit
from volve_ops.domain.well_naming import UnresolvedWellName, well_of
from volve_ops.extraction.sampling import HOLD_OUT_WELLS, PRODUCTION_BOUNDARY_ISO

PRODUCTION_BOUNDARY: Final[dt.date] = dt.date.fromisoformat(PRODUCTION_BOUNDARY_ISO)


class LeakageFinding(BaseModel):
    """One way the hold-out was reached. An incident, not a deduction from a score."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    check: str
    detail: str


class LeakageAudit(BaseModel):
    """What the five checks found, and what each one examined.

    `examined` is reported beside every check because a check that passed over an empty set is not
    the same as a check that passed, and this project has already published one pass mark that could
    not fail.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    examined: dict[str, int]
    findings: tuple[LeakageFinding, ...] = ()

    @property
    def clean(self) -> bool:
        return not self.findings

    @property
    def vacuous_checks(self) -> tuple[str, ...]:
        """Checks that examined nothing, and so demonstrate nothing."""
        return tuple(name for name, count in sorted(self.examined.items()) if count == 0)


def _hold_out_wells_in(wells: Iterable[str]) -> list[str]:
    """Hold-out wells among these, matched on the well rather than the whole string.

    `15/9-F-5 C` would be a wellbore of the hold-out well `15/9-F-5`, and a check comparing whole
    strings would miss it.

    `well_of` decides it where it can. Where it raises, on a name outside the project's naming
    convention, a prefix test stands in: a wellbore of a hold-out well is `"15/9-F-5" + " " +
    suffix`, so the space is required and `15/9-F-50` does not match.

    The prefix test runs **only** in that fallback. An earlier version ran it unconditionally and so
    overrode a successful resolution, which review showed made `15/9-F-50`, `15/9-F-5X` and
    `15/9-F-9B` false positives. Harmless against today's hold-out set, and not harmless if a
    single-digit well ever entered it: `15/9-F-1` would then capture F-11, F-12, F-14 and F-15 and
    the audit would call four development producers held out.
    """
    found: set[str] = set()
    for well in wells:
        if well in HOLD_OUT_WELLS:
            found.add(well)
            continue
        try:
            if well_of(well) in HOLD_OUT_WELLS:
                found.add(well)
        except UnresolvedWellName:
            if any(well.startswith(h + " ") for h in HOLD_OUT_WELLS):
                found.add(well)
    return sorted(found)


def audit(
    *,
    fitted_wells: Iterable[str],
    fitted_days: Mapping[str, Sequence[str]],
    split: TemporalSplit,
    labelled_report_dates: Mapping[str, dt.date],
    labelled_wells: Iterable[str],
    corrections: Iterable[Mapping[str, object]] = (),
    investigated_wells: Iterable[str] = (),
    label_dir: Path | None = None,
) -> LeakageAudit:
    """Run all five checks of section 19.2.

    `fitted_days` maps a well to the ISO dates a script recorded having fitted or swept on, read
    from that script's run manifest. It must not be recomputed by the caller: see the module
    docstring for what happened when it was.
    """
    findings: list[LeakageFinding] = []
    examined: dict[str, int] = {}

    # 1. No section 16 hold-out well carries a label or an investigation.
    #
    #    Corrected by protocol amendment 5. It once covered production fits too, which applied the
    #    drilling layer's by-well hold-out to a layer section 10 splits temporally. Nothing leaks by
    #    fitting production on a well whose drilling reports are held out: the layers share no data.
    #    Check 3 audits production fitting.
    #
    #    `fitted_wells` is context rather than a check, and is reported as such: it generates no
    #    finding, so counting it under `examined` would claim an audit that is not happening.
    examined["context_wells_fitted_not_a_check"] = len(list(fitted_wells))
    labelled = list(labelled_wells)
    examined["hold_out_well_in_a_label"] = len(labelled)
    for well in _hold_out_wells_in(labelled):
        findings.append(
            LeakageFinding(
                check="hold_out_well_in_a_label",
                detail=f"{well} is a hold-out well and carries a label",
            )
        )

    # 2. No labelled report falls after the production boundary, on any well.
    examined["labelled_report_after_the_boundary"] = len(labelled_report_dates)
    late = sorted(
        (event_id, when)
        for event_id, when in labelled_report_dates.items()
        if when > PRODUCTION_BOUNDARY
    )
    for event_id, when in late:
        findings.append(
            LeakageFinding(
                check="labelled_report_after_the_boundary",
                detail=f"{event_id} is dated {when}, after the {PRODUCTION_BOUNDARY} boundary",
            )
        )

    # 3. Every date a script recorded fitting on passes the split's own test.
    total_days = sum(len(days) for days in fitted_days.values())
    examined["fitted_day_outside_development"] = total_days
    if total_days == 0:
        findings.append(
            LeakageFinding(
                check="fitted_day_outside_development",
                detail="no script recorded the dates it fitted on, so this check has nothing to "
                "audit; a run that cannot be audited is not a clean run",
            )
        )
    for well, dates in sorted(fitted_days.items()):
        outside = sorted(d for d in dates if not split.is_development(dt.date.fromisoformat(d)))
        if outside:
            findings.append(
                LeakageFinding(
                    check="fitted_day_outside_development",
                    detail=f"{well}: {len(outside)} recorded fitted dates are outside the "
                    f"development window, first {outside[0]}",
                )
            )

    # 4. No correction in force derives from a hold-out event.
    corrections_list = list(corrections)
    examined["correction_from_the_hold_out"] = len(corrections_list)
    for correction in corrections_list:
        well = str(correction.get("well", ""))
        if well and _hold_out_wells_in([well]):
            findings.append(
                LeakageFinding(
                    check="correction_from_the_hold_out",
                    detail=f"a correction derives from {well}, a hold-out well",
                )
            )

    # 5. No hold-out well reaches an investigation at all, as a subject or as context.
    #
    #    `investigated_wells` must be every well in the bundle population, not only the wells that
    #    produced a finding. Review found 15/9-F-5 in the population of all fourteen findings, where
    #    the offset comparison reads it, while producing no finding of its own and so being
    #    invisible
    #    to a check that looked at findings.
    investigated = sorted(set(investigated_wells))
    examined["hold_out_well_reaches_an_investigation"] = len(investigated)
    for well in _hold_out_wells_in(investigated):
        findings.append(
            LeakageFinding(
                check="hold_out_well_reaches_an_investigation",
                detail=f"{well} is a hold-out well and is in the population an investigation reads",
            )
        )
    candidates = sorted(label_dir.glob("*hold*out*")) if label_dir is not None else []
    examined["hold_out_label_file_exists"] = (
        len(list(label_dir.iterdir())) if label_dir is not None else 0
    )
    for path in candidates:
        findings.append(
            LeakageFinding(
                check="hold_out_label_file_exists",
                detail=f"{path.name} exists; section 16 reserves hold-out labels for Phase 8",
            )
        )

    return LeakageAudit(examined=examined, findings=tuple(findings))
