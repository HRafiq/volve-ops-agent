"""Run tracking. The manifest is the durable artifact; MLflow is optional on top of it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from volve_ops.observability.tracking import MLFLOW_URI_ENV, log_run, mlflow_available


def test_a_run_is_recorded_to_a_file_without_any_tracking_server(tmp_path: Path) -> None:
    """A run record that only exists inside a server is one a reader of the repo cannot see."""
    manifest = tmp_path / "run.json"
    payload = log_run(
        name="extraction",
        params={"extractor_version": "extractor-v0", "events": 3673},
        metrics={"macro_f1": 0.42},
        manifest_path=manifest,
    )
    assert manifest.is_file()
    written = json.loads(manifest.read_text())
    assert written["params"]["events"] == 3673
    assert written["metrics"]["macro_f1"] == 0.42
    assert payload["mlflow"] is False


def test_parameters_and_metrics_stay_apart(tmp_path: Path) -> None:
    """A tracker that conflates them lets a threshold be recorded as though it were a result."""
    log_run(
        name="r",
        params={"threshold": 0.2},
        metrics={"observed": 0.31},
        manifest_path=tmp_path / "run.json",
    )
    written = json.loads((tmp_path / "run.json").read_text())
    assert "threshold" in written["params"]
    assert "threshold" not in written["metrics"]


def test_tracking_is_off_unless_a_uri_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(MLFLOW_URI_ENV, raising=False)
    assert mlflow_available() is False


def test_the_manifest_directory_is_created(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deeper" / "run.json"
    log_run(name="r", params={}, metrics={}, manifest_path=target)
    assert target.is_file()
