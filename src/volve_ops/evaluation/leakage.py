"""The leakage audit of protocol section 19.2.

The Phase 4 gate is "dev results table; hold-out untouched". Untouched is a claim, and a claim about
one's own discipline is the kind most worth checking mechanically, because the failure mode is not
dishonesty but forgetting: a filter applied one call too late, a well that looks like a development
well because it never appears in the output.

Five checks, all gating. A failure is an incident rather than a score: the affected result is
withdrawn, not reported with a caveat.

One shape is worth naming because it is the realistic one. Check 3 asks whether a day set came from
the split filter or was filtered afterwards. Those produce the same days today and will not when
someone adds a code path fitting on `history.for_well(...)` directly, which is one autocomplete
away from `development_only(history.for_well(...), split)`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.domain.day_class import ClassifiedDay
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

    `15/9-F-5 AY1H` is a wellbore of the hold-out well `15/9-F-5`, and a check comparing whole
    strings would miss it.

    Three ways of matching, in order, because this is a gate and a gate must not be defeatable by
    an input it does not recognise. `well_of` is tried first and raises on a name outside the
    project's naming convention, so the fallback is a prefix test: an unfamiliar wellbore of a
    hold-out well still matches. Failing closed matters more here than being precise, because the
    cost of a false positive is a sentence of explanation and the cost of a false negative is a
    published result scored on held-out data.
    """
    found: set[str] = set()
    for well in wells:
        if well in HOLD_OUT_WELLS:
            found.add(well)
            continue
        try:
            resolved = well_of(well)
        except UnresolvedWellName:
            resolved = None
        if resolved in HOLD_OUT_WELLS or any(well.startswith(h) for h in HOLD_OUT_WELLS):
            found.add(well)
    return sorted(found)


def audit(
    *,
    fitted_wells: Iterable[str],
    fitted_days: Mapping[str, Sequence[ClassifiedDay]],
    split: TemporalSplit,
    labelled_report_dates: Mapping[str, dt.date],
    labelled_wells: Iterable[str],
    corrections: Iterable[Mapping[str, object]] = (),
    investigated_wells: Iterable[str] = (),
    label_dir: Path | None = None,
) -> LeakageAudit:
    """Run all five checks of section 19.2.

    `fitted_days` is the day set every expectation fit and threshold choice actually ran on, keyed
    by well. It is passed in rather than recomputed so the audit examines what the run used,
    not what it should have used, which is the only version worth auditing.
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
    #    `fitted_wells` is still counted, because a well that was fitted and also carries a label is
    #    worth seeing in the examined counts, but it no longer generates a finding on its own.
    examined["wells_fitted"] = len(list(fitted_wells))
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

    # 3. Every fitted day passes the split's own test. This is the check that catches a filter
    #    applied one call too late rather than at the source.
    total_days = sum(len(days) for days in fitted_days.values())
    examined["fitted_day_outside_development"] = total_days
    for well, days in sorted(fitted_days.items()):
        outside = [d for d in days if not split.is_development(d.day.production_date)]
        if outside:
            findings.append(
                LeakageFinding(
                    check="fitted_day_outside_development",
                    detail=f"{well}: {len(outside)} fitted days are not development days, "
                    f"first {outside[0].day.production_date}",
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

    # 5. No hold-out episode investigated, and no hold-out label file on disk.
    investigated = list(investigated_wells)
    examined["hold_out_episode_investigated"] = len(investigated)
    for well in _hold_out_wells_in(investigated):
        findings.append(
            LeakageFinding(
                check="hold_out_episode_investigated",
                detail=f"{well} is a hold-out well and has been investigated",
            )
        )
    present = sorted(label_dir.glob("hold-out*")) if label_dir is not None else []
    examined["hold_out_label_file_exists"] = 1 if label_dir is not None else 0
    for path in present:
        findings.append(
            LeakageFinding(
                check="hold_out_label_file_exists",
                detail=f"{path.name} exists; section 16 reserves hold-out labels for Phase 8",
            )
        )

    return LeakageAudit(examined=examined, findings=tuple(findings))
