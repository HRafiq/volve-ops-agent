"""The MCP adapter, exercised through the protocol rather than by hand.

The repository's own standard, from the evaluation protocol: a manual check is not a guarantee.
The adapter is the only surface a remote host touches, so its refusals are worth a test.

Skipped when the optional extra is absent, so the cheap CI job does not need a protocol server.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp", reason="the MCP adapter is an optional extra")

from source_schema import book, row  # noqa: E402


@pytest.fixture
def workbook(tmp_path: Path) -> Path:
    return book(
        tmp_path,
        [
            row(DATEPRD=dt.datetime(2010, 1, 1) + dt.timedelta(days=i), BORE_OIL_VOL=2400.0)
            for i in range(30)
        ],
    )


def call(name: str, **kwargs: str) -> dict[str, Any]:
    from volve_ops.mcp_server import server

    async def run() -> dict[str, Any]:
        out = await server.mcp.call_tool(name, kwargs)
        blob = out[0][0] if isinstance(out, tuple) else out[0]
        parsed: dict[str, Any] = json.loads(blob.text)
        return parsed

    return asyncio.run(run())


@pytest.fixture(autouse=True)
def configured(workbook: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from volve_ops.mcp_server import server

    monkeypatch.setenv(server.WORKBOOK_ENV, str(workbook))
    server._cache.clear()


def test_a_well_formed_request_returns_a_typed_result() -> None:
    payload = call("production_history", well="15/9-F-12", start="2010-01-01", end="2010-01-30")
    assert payload["error"] is None
    assert payload["value"]["valid_producing_days"] == 30


@pytest.mark.parametrize(
    ("start", "end", "code"),
    [
        ("not-a-date", "2010-01-30", "invalid_range"),
        ("2010-13-01", "2010-01-30", "invalid_range"),
        ("2010-01-30", "2010-01-01", "invalid_range"),
        ("2010-01-01", "2020-01-01", "range_too_large"),
    ],
)
def test_bad_arguments_come_back_as_codes_not_tracebacks(start: str, end: str, code: str) -> None:
    """A malformed date used to escape the schema as free text an agent could not branch on."""
    payload = call("production_history", well="15/9-F-12", start=start, end=end)
    assert payload["value"] is None
    assert payload["error"]["code"] == code


def test_an_unknown_well_is_refused_with_its_code() -> None:
    payload = call("data_quality", well="15/9-NOPE", start="2010-01-01", end="2010-01-30")
    assert payload["error"]["code"] == "unknown_well"


def test_an_invalid_request_does_not_parse_the_workbook() -> None:
    """Validation before loading: the cheapest bad request should not cost the dearest work."""
    from volve_ops.mcp_server import server

    server._cache.clear()
    call("production_history", well="15/9-F-12", start="not-a-date", end="2010-01-30")
    assert not server._cache

    call("production_history", well="15/9-F-12", start="2010-01-01", end="2010-01-30")
    assert len(server._cache) == 1


def test_the_workbook_is_parsed_once_across_calls() -> None:
    from volve_ops.mcp_server import server

    call("production_history", well="15/9-F-12", start="2010-01-01", end="2010-01-30")
    first = next(iter(server._cache.values()))
    call("data_quality", well="15/9-F-12", start="2010-01-01", end="2010-01-30")
    assert next(iter(server._cache.values())) is first


def test_a_missing_configuration_is_a_typed_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    from volve_ops.mcp_server import server

    monkeypatch.delenv(server.WORKBOOK_ENV, raising=False)
    payload = call("data_quality", well="15/9-F-12", start="2010-01-01", end="2010-01-30")
    assert payload["error"]["code"] == "no_data"


def test_both_tools_are_advertised() -> None:
    from volve_ops.mcp_server import server

    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == {"production_history", "data_quality"}
