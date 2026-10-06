"""Run tracking, writing to MLflow when it is configured and to a file always.

The handoff asks for MLflow so extraction and evaluation runs can be compared across versions.
It is optional here for the same reason the MCP adapter is: the deterministic test suite should
not need a tracking server, and a run record that only exists inside one is a run record a
reader of this repository cannot see.

So every run writes a JSON manifest regardless, and additionally logs to MLflow if the extra is
installed and a tracking URI is set. The manifest is the durable artifact; MLflow is the
convenience on top of it.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

MLFLOW_URI_ENV = "MLFLOW_TRACKING_URI"


def mlflow_available() -> bool:
    """Whether MLflow is installed and pointed somewhere."""
    if not os.environ.get(MLFLOW_URI_ENV):
        return False
    try:
        import mlflow  # noqa: F401
    except ImportError:
        return False
    return True


def log_run(
    *,
    name: str,
    params: Mapping[str, Any],
    metrics: Mapping[str, float],
    manifest_path: Path,
    tags: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Record one run. Returns what was written.

    Metrics and parameters are kept apart because they mean different things: a parameter is
    something chosen, a metric something measured, and a tracking system that conflates them
    lets a threshold be recorded as though it were a result.
    """
    payload: dict[str, Any] = {
        "run": name,
        "recorded_at": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
        "params": dict(params),
        "metrics": dict(metrics),
        "tags": dict(tags or {}),
        "mlflow": False,
    }

    if mlflow_available():
        import mlflow

        mlflow.set_tracking_uri(os.environ[MLFLOW_URI_ENV])
        with mlflow.start_run(run_name=name):
            for key, value in params.items():
                mlflow.log_param(key, value)
            for key, value in metrics.items():
                mlflow.log_metric(key, value)
            for key, value in (tags or {}).items():
                mlflow.set_tag(key, value)
            mlflow.log_dict(payload, "run.json")
        payload["mlflow"] = True

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return payload
