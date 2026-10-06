"""The workbook reader: the only module that knows the source's column names."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from openpyxl import Workbook

from volve_ops.ingest.production import WellStatus
from volve_ops.ingest.production_reader import (
    DAILY_SHEET,
    SourceSchemaError,
    read_daily_production,
)

HEADER = [
    "DATEPRD",
    "NPD_WELL_BORE_NAME",
    "ON_STREAM_HRS",
    "BORE_OIL_VOL",
    "BORE_GAS_VOL",
    "BORE_WAT_VOL",
    "AVG_CHOKE_SIZE_P",
    "AVG_CHOKE_UOM",
    "FLOW_KIND",
    "WELL_TYPE",
]


def book(tmp_path: Path, rows: list[list[object]], sheet: str = DAILY_SHEET) -> Path:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = sheet
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    path = tmp_path / "wb.xlsx"
    wb.save(path)
    return path


def row(**over: object) -> list[object]:
    base: dict[str, object] = {
        "DATEPRD": dt.datetime(2010, 6, 1),
        "NPD_WELL_BORE_NAME": "15/9-F-12",
        "ON_STREAM_HRS": 24.0,
        "BORE_OIL_VOL": 900.0,
        "BORE_GAS_VOL": 1000.0,
        "BORE_WAT_VOL": 10.0,
        "AVG_CHOKE_SIZE_P": 50.0,
        "AVG_CHOKE_UOM": "%",
        "FLOW_KIND": "production",
        "WELL_TYPE": "OP",
    }
    base.update(over)
    return [base[c] for c in HEADER]


def test_reads_a_row_into_canonical_form(tmp_path: Path) -> None:
    (day,) = read_daily_production(book(tmp_path, [row()]))
    assert day.well == "15/9-F-12"
    assert day.production_date == dt.date(2010, 6, 1)
    assert day.on_stream_hours == 24.0
    assert day.well_status is WellStatus.PRODUCING


def test_an_empty_numeric_cell_becomes_none_and_never_a_zero_or_a_nan(tmp_path: Path) -> None:
    """The reason this module uses openpyxl rather than pandas."""
    (day,) = read_daily_production(book(tmp_path, [row(ON_STREAM_HRS=None, BORE_OIL_VOL=None)]))
    assert day.on_stream_hours is None
    assert day.oil_volume_sm3 is None


def test_flow_kind_decides_status_not_well_type(tmp_path: Path) -> None:
    """The two columns disagree on 18 rows of the real workbook; the day's flow wins."""
    (day,) = read_daily_production(book(tmp_path, [row(FLOW_KIND="production", WELL_TYPE="WI")]))
    assert day.well_status is WellStatus.PRODUCING
    (inj,) = read_daily_production(book(tmp_path, [row(FLOW_KIND="injection", WELL_TYPE="OP")]))
    assert inj.well_status is WellStatus.INJECTING


def test_an_unmapped_flow_kind_is_an_error_not_a_guess(tmp_path: Path) -> None:
    with pytest.raises(SourceSchemaError, match="unmapped FLOW_KIND"):
        list(read_daily_production(book(tmp_path, [row(FLOW_KIND="testing")])))


def test_a_non_numeric_cell_in_a_numeric_column_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SourceSchemaError, match="not a number"):
        list(read_daily_production(book(tmp_path, [row(ON_STREAM_HRS="twenty-four")])))


def test_a_boolean_is_not_accepted_as_a_number(tmp_path: Path) -> None:
    with pytest.raises(SourceSchemaError, match="boolean"):
        list(read_daily_production(book(tmp_path, [row(BORE_OIL_VOL=True)])))


def test_a_bad_date_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SourceSchemaError, match="not a date"):
        list(read_daily_production(book(tmp_path, [row(DATEPRD="yesterday")])))


def test_a_row_without_a_well_name_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SourceSchemaError, match="no well name"):
        list(read_daily_production(book(tmp_path, [row(NPD_WELL_BORE_NAME="  ")])))


def test_a_missing_sheet_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SourceSchemaError, match="no sheet named"):
        list(read_daily_production(book(tmp_path, [row()], sheet="Something Else")))


def test_a_missing_column_is_refused_rather_than_worked_around(tmp_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = DAILY_SHEET
    ws.append([c for c in HEADER if c != "ON_STREAM_HRS"])
    path = tmp_path / "short.xlsx"
    wb.save(path)
    with pytest.raises(SourceSchemaError, match="missing expected columns"):
        list(read_daily_production(path))


def test_fully_blank_rows_are_skipped(tmp_path: Path) -> None:
    days = list(read_daily_production(book(tmp_path, [row(), [None] * len(HEADER), row()])))
    assert len(days) == 2
