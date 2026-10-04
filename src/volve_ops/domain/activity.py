"""Dates on which a well has a drilling, completion or intervention record.

Section 7 disqualifies a stable reference window containing one, because the well was being
worked on and whatever the production did during it is not a baseline for anything.

Dates come from the daily drilling report corpus, which files one report per wellbore per day.
The join to production is by canonical well name, and it has to be: the two sources spell the
same wellbore differently, and an unmatched name would make a window look activity-free when
it is not.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from pathlib import Path

from volve_ops.domain.well_naming import UnresolvedWellName, canonical_from_ddr_token, well_of

_REPORT_FILENAME = re.compile(r"^(?P<well>.+)_(?P<y>\d{4})_(?P<m>\d{2})_(?P<d>\d{2})\.xml$")


def activity_dates_by_well(report_dir: Path) -> dict[str, set[dt.date]]:
    """Map canonical well to the dates it has a drilling report on.

    Keyed by well rather than wellbore, so that drilling a sidetrack disqualifies windows on
    its siblings. That is the conservative reading of section 7: work on one wellbore of a well
    can disturb production from another.

    A filename that cannot be resolved to a canonical well raises, rather than being skipped.
    Skipping would silently remove activity and make a disturbed window look stable.
    """
    dates: dict[str, set[dt.date]] = defaultdict(set)
    for path in sorted(report_dir.glob("*.xml")):
        match = _REPORT_FILENAME.match(path.name)
        if not match:
            raise UnresolvedWellName(f"unrecognised drilling-report filename: {path.name}")
        wellbore = canonical_from_ddr_token(match["well"])
        day = dt.date(int(match["y"]), int(match["m"]), int(match["d"]))
        dates[well_of(wellbore)].add(day)
    return dict(dates)
