"""Expose the production tools over MCP.

The rule this file exists to respect: MCP is an adapter, not the architecture. Each function
parses its arguments, calls a tool in `volve_ops.tools`, and hands back what it returned. If a
rule about what a caller may ask for ever appears here, it has been written twice, and the two
copies will disagree.

Two things the adapter does have to own, because they only exist at this boundary.

Arguments arrive as strings over a protocol, so the date parse happens here, and its failure
has to come back as the same typed refusal the tool layer would produce. An agent that receives
a stack trace in prose for a bad date and a structured code for a bad range cannot branch on
either.

And the workbook is parsed once, not per call. It takes about a second and 90 MB, the server
runs sync tools inline on the event loop, and validation used to happen after the load, so the
cheapest invalid request cost the most expensive operation and stalled every other caller while
it did. Arguments are checked first now, and the parsed history is cached against the file's
path, size and modification time.

No `from __future__ import annotations` here, deliberately. Pinned mcp 1.9.4 calls `issubclass`
on raw annotations while building each tool's schema, which raises on the strings that
postponed evaluation produces. That is a bug in the pinned version rather than a property of
MCP, so a version bump may lift the constraint. The rest of the project keeps the import.
"""

import datetime as dt
import os
from pathlib import Path
from typing import Any

from volve_ops.domain.production_service import ProductionHistory, load_volve_production
from volve_ops.tools.production_tools import (
    build_range,
    get_data_quality,
    get_production_history,
)
from volve_ops.tools.schemas import ToolError, ToolErrorCode, ToolResult

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - exercised only without the optional extra
    raise ImportError(
        "the MCP adapter needs the optional dependency: pip install 'volve-ops-agent[mcp]'"
    ) from exc

WORKBOOK_ENV = "VOLVE_PRODUCTION_WORKBOOK"

mcp = FastMCP("volve-ops")

_cache: dict[tuple[str, int, float], ProductionHistory] = {}


def _refuse(code: ToolErrorCode, message: str, **detail: str) -> dict[str, Any]:
    return ToolResult[None](error=ToolError(code=code, message=message, detail=detail)).model_dump(
        mode="json"
    )


def _parse_date(value: str, field: str) -> dt.date | dict[str, Any]:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        return _refuse(
            ToolErrorCode.INVALID_RANGE,
            f"{field} is not an ISO date (YYYY-MM-DD): {exc}",
            field=field,
            value=value,
        )


def _history() -> ProductionHistory | dict[str, Any]:
    """The configured workbook, parsed once per version of the file.

    Read from the environment rather than taken as a tool argument. A caller that can name an
    arbitrary path can read an arbitrary file, and nothing about an investigation requires
    choosing a dataset per request.
    """
    configured = os.environ.get(WORKBOOK_ENV)
    if not configured:
        return _refuse(
            ToolErrorCode.NO_DATA, f"{WORKBOOK_ENV} is not set on the server", setting=WORKBOOK_ENV
        )
    path = Path(configured)
    try:
        stat = path.stat()
    except OSError as exc:
        return _refuse(
            ToolErrorCode.NO_DATA, f"{WORKBOOK_ENV} does not point at a readable file: {exc}"
        )

    key = (str(path), stat.st_size, stat.st_mtime)
    cached = _cache.get(key)
    if cached is None:
        try:
            cached = load_volve_production(path)
        except Exception as exc:
            return _refuse(
                ToolErrorCode.NO_DATA,
                f"the configured workbook could not be read: {type(exc).__name__}",
            )
        _cache.clear()
        _cache[key] = cached
    return cached


@mcp.tool()
def production_history(well: str, start: str, end: str) -> dict[str, Any]:
    """Classified daily production for one well over a bounded date range."""
    parsed_start = _parse_date(start, "start")
    if isinstance(parsed_start, dict):
        return parsed_start
    parsed_end = _parse_date(end, "end")
    if isinstance(parsed_end, dict):
        return parsed_end

    window = build_range(parsed_start, parsed_end)
    if isinstance(window, ToolError):
        return ToolResult[None](error=window).model_dump(mode="json")

    history = _history()
    if isinstance(history, dict):
        return history
    return get_production_history(history, well, parsed_start, parsed_end).model_dump(mode="json")


@mcp.tool()
def data_quality(well: str, start: str, end: str) -> dict[str, Any]:
    """What a conclusion over this range would rest on: gaps, quarantines, usable days."""
    parsed_start = _parse_date(start, "start")
    if isinstance(parsed_start, dict):
        return parsed_start
    parsed_end = _parse_date(end, "end")
    if isinstance(parsed_end, dict):
        return parsed_end

    window = build_range(parsed_start, parsed_end)
    if isinstance(window, ToolError):
        return ToolResult[None](error=window).model_dump(mode="json")

    history = _history()
    if isinstance(history, dict):
        return history
    return get_data_quality(history, well, parsed_start, parsed_end).model_dump(mode="json")


def main() -> None:  # pragma: no cover - process entry point
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
