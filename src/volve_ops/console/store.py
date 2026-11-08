"""Reading the run artifacts the console serves. Protocol section 21.1.

One place that knows where the manifests and the per-episode artifacts live, so that nothing else
has to, and so that "the console reads what the harnesses wrote" is a single import rather than a
convention. Nothing here computes a figure. The only arithmetic is slicing a series by date, which
is selection and not derivation.

A missing artifact is an error and not an empty payload. A console that renders an investigation
with no series, no facts and no finding would show an operator a screen that looks like an answer,
and section 21.6 mark 1 would pass over it because a payload with no figures has no unsourced ones.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from volve_ops.evaluation.table import MANIFESTS

#: Where the harnesses write. Overridable for a test, fixed for a run.
DEFAULT_CACHE: Final[Path] = Path("data/cache")
DEFAULT_TRACES: Final[Path] = Path("data/cache/investigations")


class ArtifactMissing(Exception):
    """An artifact the console needs was not written. Nothing is served without it."""


class EpisodeArtifacts(BaseModel):
    """The four files one episode produced, as read from disk."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    investigation_id: str
    finding: Mapping[str, Any]
    facts: tuple[Mapping[str, Any], ...]
    series: tuple[Mapping[str, Any], ...]
    trace: Mapping[str, Any]

    @property
    def fact_ids(self) -> frozenset[str]:
        """Every id the ledger defines, which is what a payload may cite.

        The ids a *finding* mentions are not the same set. A finding naming `fact_000009` when the
        ledger holds three facts is exactly the defect persisting the ledger exists to expose, so
        the resolvable set comes from the ledger.
        """
        return frozenset(str(f["id"]) for f in self.facts)


def slug_for(well: str, onset: str) -> str:
    """The filename the investigation harness writes, derived the same way it derives it."""
    return f"{well.replace('/', '_').replace(' ', '_')}_{onset}"


def investigation_id(well: str, onset: str) -> str:
    """A URL-safe id for one episode. Stable, and derived from the episode rather than a counter."""
    return slug_for(well, onset)


class RunStore:
    """Every artifact the console serves, read once."""

    def __init__(self, cache: Path = DEFAULT_CACHE, traces: Path = DEFAULT_TRACES) -> None:
        self.cache = cache
        self.traces = traces

    def _read(self, path: Path) -> Any:
        if not path.exists():
            raise ArtifactMissing(
                f"{path} has not been written; run the harness that produces it before serving "
                "a screen that reads it, because an empty screen looks like an answer"
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def manifests(self) -> dict[str, Mapping[str, Any]]:
        """The five run manifests, by the name the results table refers to them by.

        The same `MANIFESTS` map the section 19.3 coverage gate uses, so a source string that
        resolves for the console resolves for the gate and the two cannot drift apart.
        """
        return {name: self._read(self.cache / file) for name, file in MANIFESTS.items()}

    def evaluation(self) -> Mapping[str, Any]:
        """The evaluation harness's own manifest.

        Read separately rather than added to `MANIFESTS`, because that map is the input set the
        section 19.3 coverage gate walks: putting the evaluation run's own output into it would
        have the gate demand table rows for the figures the gate itself produces.
        """
        result: Mapping[str, Any] = self._read(self.cache / "evaluation_run.json")
        return result

    def security(self) -> Mapping[str, Any]:
        """The section 22 run, which the System Health workspace renders.

        Read separately rather than added to `MANIFESTS`, for the reason `evaluation` gives: that
        map is the section 19.3 coverage gate's input set, and putting a gate's own output into it
        would have the gate demand results-table rows for the figures it produced.
        """
        result: Mapping[str, Any] = self._read(self.cache / "security_run.json")
        return result

    def ablations(self) -> Mapping[str, Any]:
        """The section 22.7 ablations. Same reasoning as `security`."""
        result: Mapping[str, Any] = self._read(self.cache / "ablation_run.json")
        return result

    def health_manifests(self) -> dict[str, Mapping[str, Any]]:
        """Every manifest a health figure may be sourced to.

        The five of `MANIFESTS` plus the two section 22 runs, so a source on the health screen
        resolves under mark 1 exactly as a source on any other screen does. `MANIFESTS` itself is
        untouched: adding to it changes what section 19.3 audits.
        """
        return {**self.manifests(), "security": self.security(), "ablation": self.ablations()}

    def episodes(self) -> list[Mapping[str, Any]]:
        """The investigation manifest's finding rows, which are the queue's source."""
        manifest = self._read(self.cache / MANIFESTS["investigation"])
        rows: list[Mapping[str, Any]] = list(manifest["findings"])
        return rows

    def artifacts_for(self, well: str, onset: str) -> EpisodeArtifacts:
        slug = slug_for(well, onset)
        return EpisodeArtifacts(
            investigation_id=investigation_id(well, onset),
            finding=self._read(self.traces / f"{slug}.finding.json"),
            facts=tuple(self._read(self.traces / f"{slug}.facts.json")),
            series=tuple(self._read(self.traces / f"{slug}.series.json")),
            trace=self._read(self.traces / f"{slug}.trace.json"),
        )

    def event_ids(self, version: str = "extractor-v0") -> frozenset[str]:
        """Every event id the store holds, which is what a cited document span resolves against.

        Not the ids a finding mentions. A finding citing an event the store does not hold is the
        defect section 18.6's provenance gate exists to catch, so the resolvable set comes from the
        store and a payload citing anything else fails mark 1.
        """
        from volve_ops.extraction.store import EventStore

        return frozenset(e.event_id for e in EventStore(self.cache / "npt_store").read(version))

    def resolvable_ids(self, well: str, onset: str) -> frozenset[str]:
        """The ledger's fact ids for this episode, plus every event id in the store."""
        return self.artifacts_for(well, onset).fact_ids | self.event_ids()

    def by_id(self, wanted: str) -> Mapping[str, Any]:
        """One finding row, by the id the queue published for it."""
        for row in self.episodes():
            if investigation_id(str(row["well"]), str(row["onset"])) == wanted:
                return row
        raise ArtifactMissing(f"no investigation with id {wanted!r}")
