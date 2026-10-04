"""Expose the production tools over MCP.

The rule this file exists to respect: MCP is an adapter, not the architecture. Every function
below is a few lines that unpack arguments, call a tool in `volve_ops.tools`, and hand back
what it returned. If a rule about what a caller may ask for ever appears here, it has been
written twice, and the two copies will disagree.

The dependency is optional. `pip install volve-ops-agent[mcp]` adds it; without it the import
below fails with a message saying so, and nothing else in the project is affected. The
deterministic test suite does not need it, which keeps the cheap CI job cheap.
"""

# No `from __future__ import annotations` here, deliberately. FastMCP introspects the
# annotations at decoration time to build each tool's schema, and postponed evaluation turns
# them into strings that its introspection cannot read. The rest of the project keeps the
# import; this module is the one place a framework's requirements reach back into the code.

import datetime as dt
import os
from pathlib import Path
from typing import Any

from volve_ops.domain.production_service import load_volve_production
from volve_ops.tools.production_tools import (
    get_data_quality,
    get_production_history,
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - exercised only without the optional extra
    raise ImportError(
        "the MCP adapter needs the optional dependency: pip install 'volve-ops-agent[mcp]'"
    ) from exc

WORKBOOK_ENV = "VOLVE_PRODUCTION_WORKBOOK"

mcp = FastMCP("volve-ops")


def _workbook() -> Path:
    """The configured production workbook.

    Read from the environment rather than taken as a tool argument. A caller that can name an
    arbitrary path can read an arbitrary file, and nothing about an investigation requires
    choosing a dataset per request.
    """
    configured = os.environ.get(WORKBOOK_ENV)
    if not configured:
        raise RuntimeError(f"set {WORKBOOK_ENV} to the production workbook path")
    path = Path(configured)
    if not path.is_file():
        raise RuntimeError(f"{WORKBOOK_ENV} does not point at a file: {path}")
    return path


@mcp.tool()
def production_history(well: str, start: str, end: str) -> dict[str, Any]:
    """Classified daily production for one well over a bounded date range."""
    history = load_volve_production(_workbook())
    result = get_production_history(
        history, well, dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    )
    return result.model_dump(mode="json")


@mcp.tool()
def data_quality(well: str, start: str, end: str) -> dict[str, Any]:
    """What a conclusion over this range would rest on: gaps, quarantines, usable days."""
    history = load_volve_production(_workbook())
    result = get_data_quality(
        history, well, dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    )
    return result.model_dump(mode="json")


def main() -> None:  # pragma: no cover - process entry point
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
