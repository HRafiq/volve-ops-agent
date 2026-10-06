"""One definition of the production workbook's columns, for tests that build one.

Two test modules each carried their own copy of this header, so extending the reader with the
sensor channels broke both of them in the same way. The reader is the only module that is allowed
to know the source's column names, and a test fixture that restates them is a second place that
knows: keeping one copy here means a column added to `COLUMNS` fails in the reader's own tests
rather than in whichever module happened to spell the header out.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from openpyxl import Workbook

from volve_ops.ingest.production_reader import COLUMNS, DAILY_SHEET

# Every column the reader requires, plus the two it cross-checks but does not map.
HEADER: list[str] = [*COLUMNS, "FLOW_KIND", "WELL_TYPE"]

#: A plausible producing day. Pressures in bar, temperatures in Celsius, as the workbook holds.
DEFAULTS: dict[str, object] = {
    "DATEPRD": dt.datetime(2010, 6, 1),
    "NPD_WELL_BORE_NAME": "15/9-F-12",
    "ON_STREAM_HRS": 24.0,
    "BORE_OIL_VOL": 900.0,
    "BORE_GAS_VOL": 1000.0,
    "BORE_WAT_VOL": 10.0,
    "AVG_CHOKE_SIZE_P": 50.0,
    "AVG_CHOKE_UOM": "%",
    "AVG_DOWNHOLE_PRESSURE": 230.0,
    "AVG_DOWNHOLE_TEMPERATURE": 103.0,
    "AVG_DP_TUBING": 175.0,
    "AVG_ANNULUS_PRESS": 16.0,
    "AVG_WHP_P": 38.0,
    "AVG_WHT_P": 80.0,
    "DP_CHOKE_SIZE": 2.4,
    "FLOW_KIND": "production",
    "WELL_TYPE": "OP",
}


def row(**over: object) -> list[object]:
    """One worksheet row, in header order, with any column overridden by keyword."""
    unknown = sorted(set(over) - set(HEADER))
    if unknown:
        raise KeyError(f"not columns of the daily sheet: {unknown}")
    values = {**DEFAULTS, **over}
    return [values[column] for column in HEADER]


def book(tmp_path: Path, rows: list[list[object]], sheet: str = DAILY_SHEET) -> Path:
    """Write a workbook holding exactly these rows."""
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = sheet
    worksheet.append(HEADER)
    for values in rows:
        worksheet.append(values)
    path = tmp_path / "wb.xlsx"
    workbook.save(path)
    return path
