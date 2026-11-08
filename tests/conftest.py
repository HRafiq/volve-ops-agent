"""Shared fixtures, and one rule about the cached dataset.

**A test that needs `data/cache/` must say so by taking a fixture from here.**

The dataset is gitignored, so it exists on a developer's machine and on no CI runner. A test that
reads it without declaring the dependency passes locally and fails on every push, which is exactly
what happened: two tests added with the Phase 6 review resolution read a run manifest directly, and
the first anyone knew of it was a string of red builds.

Writing `pytest.mark.skipif(...)` at each site works and is what the older tests do. The problem is
that it is opt-in and silent when forgotten. These fixtures are not: a test that wants
the data has to ask for one, and asking is what registers the skip. There is no way to use the data
through them and forget to declare it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from volve_ops.console.store import RunStore

#: What the harnesses write, and what a runner does not have.
CACHE: Final[Path] = Path("data/cache")
INVESTIGATION_RUN: Final[Path] = CACHE / "investigation_run.json"
WORKBOOK: Final[Path] = CACHE / "Volve production data.xlsx"
REPORTS: Final[Path] = CACHE / "ddr_xml"
TRACES: Final[Path] = CACHE / "investigations"


@pytest.fixture
def cached_runs() -> RunStore:
    """A `RunStore` over the cached run artifacts, or a skip when they are absent."""
    missing = [p for p in (INVESTIGATION_RUN, TRACES) if not p.exists()]
    if missing:
        pytest.skip(f"needs the cached run artifacts; absent: {[str(p) for p in missing]}")
    return RunStore()


@pytest.fixture
def cached_dataset() -> tuple[Path, Path]:
    """The workbook and the drilling reports, or a skip when they are absent."""
    missing = [p for p in (WORKBOOK, REPORTS) if not p.exists()]
    if missing:
        pytest.skip(f"needs the cached dataset; absent: {[str(p) for p in missing]}")
    return WORKBOOK, REPORTS
