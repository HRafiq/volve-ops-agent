"""What the process actually did, observed rather than argued from the code.

Protocol section 22.4 mark 4 requires that no file outside the declared data directories is
opened during an injection run, and that the observation is made **during the run**. A test that
reads the source and concludes no path is constructed has tested the source. This module
installs a CPython audit hook and records the file opens, network connections, subprocess
launches and dynamic compilations that happen inside a recording window.

Three honest limits, written down because an audit hook looks more complete than it is.

**It cannot be uninstalled.** `sys.addaudithook` is permanent for the life of the process, so
recording is gated by a flag and the hook is installed once. In a test process that is fine. It
is not a sandbox and nothing here prevents an open; it witnesses one.

**The interpreter opens a great many files of its own.** Imports, bytecode caches, encodings
tables and certificate bundles all arrive as `open` events, so a bare count is meaningless. The
classification below is therefore explicit rather than a vague allow-list, because an
unfalsifiable check is the defect this project keeps finding: a path is **interpreter
territory** if it lies under `sys.prefix`, `sys.base_prefix`, the standard library, or any
`site-packages` or `__pycache__` directory. Everything else is **project territory** and is
judged against the declared roots.

**It sees paths, not intent.** A denied path recorded here means something asked for it; it does
not say which component did. The run that records it knows which payload was in flight, which is
what the report needs.
"""

from __future__ import annotations

import sys
import sysconfig
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

#: Audited events this module records. Chosen to cover section 11.5's prohibitions as well as
#: section 22.4 mark 4: file reads, network reach, shell and subprocess launch, and dynamic code.
RECORDED_EVENTS: Final[frozenset[str]] = frozenset(
    {
        "open",
        "socket.connect",
        "socket.getaddrinfo",
        "urllib.Request",
        "subprocess.Popen",
        "os.system",
        "os.exec",
        "exec",
        "compile",
    }
)

#: Paths that must never be opened during a run, by name, wherever they sit. These are the ones
#: the class 4 payloads name. A match is a violation regardless of the allow-list.
DENIED_NAMES: Final[tuple[str, ...]] = (
    "/.env",
    "/_private/",
    "/.ssh/",
    "/etc/passwd",
    "/etc/shadow",
    "/etc/hosts",
    "/.aws/",
    "/.netrc",
    "id_rsa",
    ".git/config",
)


def _interpreter_roots() -> tuple[str, ...]:
    roots = {sys.prefix, sys.base_prefix}
    for name in ("stdlib", "platstdlib", "purelib", "platlib"):
        path = sysconfig.get_path(name)
        if path:
            roots.add(path)
    return tuple(sorted(roots))


_INTERPRETER_ROOTS: Final[tuple[str, ...]] = _interpreter_roots()


def is_interpreter_territory(path: str) -> bool:
    """Whether a path belongs to the interpreter's own machinery rather than to this project."""
    if "site-packages" in path or "__pycache__" in path or path.endswith((".pyc", ".pyo")):
        return True
    return any(path.startswith(root) for root in _INTERPRETER_ROOTS)


@dataclass(frozen=True)
class AuditEvent:
    """One audited action, with the payload marker that was in flight when it happened."""

    event: str
    target: str
    marker: str | None = None

    @property
    def is_file_open(self) -> bool:
        return self.event == "open"


@dataclass
class Recorder:
    """Audited events inside a recording window."""

    events: list[AuditEvent] = field(default_factory=list)
    recording: bool = False
    marker: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def note(self, event: str, target: str) -> None:
        with self._lock:
            if self.recording:
                self.events.append(AuditEvent(event=event, target=target, marker=self.marker))

    def file_opens(self) -> tuple[str, ...]:
        return tuple(e.target for e in self.events if e.is_file_open)

    def project_file_opens(self) -> tuple[str, ...]:
        """File opens outside interpreter territory, which is what mark 4 judges."""
        return tuple(p for p in self.file_opens() if not is_interpreter_territory(p))

    def denied_opens(self) -> tuple[AuditEvent, ...]:
        """Opens of a path in `DENIED_NAMES`, wherever it sits."""
        return tuple(
            e
            for e in self.events
            if e.is_file_open and any(name in e.target for name in DENIED_NAMES)
        )

    def network_reach(self) -> tuple[AuditEvent, ...]:
        return tuple(
            e
            for e in self.events
            if e.event in {"socket.connect", "socket.getaddrinfo", "urllib.Request"}
        )

    def code_execution(self) -> tuple[AuditEvent, ...]:
        return tuple(
            e
            for e in self.events
            if e.event in {"subprocess.Popen", "os.system", "os.exec", "exec", "compile"}
        )

    def outside(self, roots: Sequence[Path]) -> tuple[AuditEvent, ...]:
        """Project-territory opens that lie under none of `roots`.

        Relative paths are resolved against the working directory, which is what an `open` with a
        relative path means, so a traversal that escapes the roots is visible here.
        """
        resolved = [str(r.resolve()) for r in roots]
        out: list[AuditEvent] = []
        for event in self.events:
            if not event.is_file_open or is_interpreter_territory(event.target):
                continue
            try:
                target = str(Path(event.target).resolve())
            except (OSError, ValueError):  # pragma: no cover - unparseable path
                out.append(event)
                continue
            if not any(target.startswith(root) for root in resolved):
                out.append(event)
        return tuple(out)


RECORDER: Final[Recorder] = Recorder()
_INSTALLED = False


def _hook(event: str, args: tuple[Any, ...]) -> None:
    if event not in RECORDED_EVENTS:
        return
    target = str(args[0]) if args else ""
    RECORDER.note(event, target)


def install() -> None:
    """Install the audit hook, once. Permanent for the process; recording is still gated."""
    global _INSTALLED
    if not _INSTALLED:
        sys.addaudithook(_hook)
        _INSTALLED = True


@contextmanager
def observing(marker: str | None = None) -> Iterator[Recorder]:
    """Record audited events for the duration of the block.

    Nested use is not supported and not needed: one payload is in flight at a time, and a nested
    window would attribute its events to the wrong marker. The recorder is cleared on entry so a
    window reports its own events and not the previous one's.
    """
    install()
    if RECORDER.recording:  # pragma: no cover - defensive
        raise RuntimeError("observation windows do not nest; one payload is in flight at a time")
    RECORDER.events.clear()
    RECORDER.marker = marker
    RECORDER.recording = True
    try:
        yield RECORDER
    finally:
        RECORDER.recording = False
        RECORDER.marker = None
