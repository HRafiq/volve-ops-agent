"""Protocol section 22.4 mark 2: the console has no unescaped-markup sink.

A property of the code rather than of a payload, and checked that way. The injection corpus can
only find a sink that some payload happens to reach; a sink introduced later on a screen no
fixture covers would pass the whole corpus. So this reads the frontend source and requires that
the sinks are simply absent.

**The rule has no exceptions, including comments and strings.** A gate that stripped comments
before scanning would let a sink hide in something shaped like one, and a gate with a list of
allowed exceptions is a gate someone will add to. The cost is that the frontend source may not
discuss these constructs even to say it avoids them, which is why that discussion is here.

What was found when this was written: one `dangerouslySetInnerHTML` in `App.tsx`, rendering the
title of a planned workspace. It was fed two literal strings and reached no document text, so no
payload could have exercised it, and it existed only to turn `&amp;` into an ampersand, which
plain JSX renders correctly on its own. It is the clearest case for this mark being a source
check: harmless on the day it was written, one prop away from being the live channel, and
invisible to every fixture in section 22.3.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Final, NamedTuple

#: Constructs that hand a string to the browser as markup or as code.
FORBIDDEN_SINKS: Final[tuple[str, ...]] = (
    "dangerouslySetInnerHTML",
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "document.write",
    "eval(",
    "new Function(",
    "javascript:",
    "srcdoc",
)

#: Files the mark reads. The built bundle is not scanned: it is generated from these, and a
#: bundler's own runtime legitimately contains some of these tokens.
SCANNED_SUFFIXES: Final[frozenset[str]] = frozenset({".ts", ".tsx", ".js", ".jsx", ".css"})

DEFAULT_FRONTEND: Final[Path] = Path("frontend/src")


class Occurrence(NamedTuple):
    file: str
    line: int
    sink: str
    text: str


def scan(root: Path = DEFAULT_FRONTEND) -> tuple[Occurrence, ...]:
    """Every forbidden sink in the frontend source."""
    return tuple(_occurrences(root))


def _occurrences(root: Path) -> Iterator[Occurrence]:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for sink in FORBIDDEN_SINKS:
                if sink in line:
                    yield Occurrence(
                        file=str(path), line=number, sink=sink, text=line.strip()[:120]
                    )


def files_scanned(root: Path = DEFAULT_FRONTEND) -> tuple[str, ...]:
    """What the mark actually read.

    Published because a scan of nothing passes. Section 21.2 learned this the hard way: a mark
    that reports examining no files is not a mark that passed, and the count is the only way a
    reader can tell the two apart.
    """
    return tuple(
        str(p) for p in sorted(root.rglob("*")) if p.is_file() and p.suffix in SCANNED_SUFFIXES
    )
