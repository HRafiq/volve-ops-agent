"""A versioned event store for extracted NPT events.

Extraction is re-run whenever the parser or the extractor changes, and a result reported from
one version must stay traceable after another has replaced it. So the store is keyed by version
rather than overwritten: a run writes a new version, previous versions stay readable, and a
manifest records what produced each one.

Events are written as JSON lines rather than a binary format. The store is derived data and is
never committed, but a human has to be able to read it when a number looks wrong, and a format
that needs a library to inspect is a format nobody inspects.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections.abc import Iterator, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from volve_ops import INGEST_VERSION
from volve_ops.extraction import EXTRACTOR_VERSION
from volve_ops.extraction.npt import NPTEvent

_VERSION_NAME = re.compile(r"[A-Za-z0-9._-]+")


class StoreManifest(BaseModel):
    """What produced one version of the store.

    Section 12 of the protocol requires a result to be traceable to a complete manifest. This is
    the extraction layer's part of it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    written_at: dt.datetime
    parser_version: str
    extractor_version: str
    source_directory: str
    source_file_count: int
    event_count: int
    content_hash: str
    wells: tuple[str, ...]

    @property
    def is_attributed(self) -> bool:
        """Whether this version carries cause attributions or only the deterministic layer."""
        return self.version.endswith("-attributed")


def content_hash(events: Sequence[NPTEvent]) -> str:
    """A digest of the events themselves, independent of the order they were written.

    Two extractions of the same reports agree on this even if the files were walked in a
    different order, so a changed digest means changed content rather than changed scheduling.
    """
    digest = hashlib.sha256()
    for line in sorted(e.model_dump_json() for e in events):
        digest.update(line.encode())
    return digest.hexdigest()


class EventStore:
    """Versioned storage for extracted events, one directory per version."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _version_dir(self, version: str) -> Path:
        # The version becomes a directory name, so it is checked here rather than in each
        # caller. A CLI that takes it positionally would otherwise read or write anywhere the
        # process can reach.
        if not _VERSION_NAME.fullmatch(version):
            raise ValueError(
                f"version {version!r} is not a plain name; letters, digits, dot, dash and "
                "underscore only"
            )
        return self.root / version

    def versions(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if (p / "manifest.json").is_file())

    def write(
        self,
        events: Sequence[NPTEvent],
        *,
        version: str,
        source_directory: Path,
        source_file_count: int,
    ) -> StoreManifest:
        """Write a version. Refuses to overwrite one that already exists.

        Refusing matters: a version silently rewritten is a version whose manifest describes
        something other than what is in it, and every result traced to it becomes a guess.
        """
        target = self._version_dir(version)
        if target.exists():
            raise FileExistsError(
                f"version {version!r} already exists; write a new version rather than "
                "replacing one results may already refer to"
            )
        target.mkdir(parents=True)

        with (target / "events.jsonl").open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(event.model_dump_json() + "\n")

        manifest = StoreManifest(
            version=version,
            written_at=dt.datetime.now(tz=dt.UTC),
            parser_version=INGEST_VERSION,
            extractor_version=EXTRACTOR_VERSION,
            source_directory=source_directory.name,
            source_file_count=source_file_count,
            event_count=len(events),
            content_hash=content_hash(events),
            wells=tuple(sorted({e.well for e in events})),
        )
        (target / "manifest.json").write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        return manifest

    def manifest(self, version: str) -> StoreManifest:
        path = self._version_dir(version) / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"no manifest for version {version!r}")
        return StoreManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def read(self, version: str) -> Iterator[NPTEvent]:
        path = self._version_dir(version) / "events.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"no events for version {version!r}")
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield NPTEvent.model_validate_json(line)

    def verify(self, version: str) -> None:
        """Raise unless the stored events still hash to what the manifest recorded."""
        recorded = self.manifest(version)
        events = list(self.read(version))
        if len(events) != recorded.event_count:
            raise ValueError(
                f"version {version!r} holds {len(events)} events, manifest says "
                f"{recorded.event_count}"
            )
        actual = content_hash(events)
        if actual != recorded.content_hash:
            raise ValueError(
                f"version {version!r} does not match its manifest: "
                f"recorded {recorded.content_hash[:16]}, found {actual[:16]}"
            )
