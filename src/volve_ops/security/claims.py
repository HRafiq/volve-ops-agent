"""Protocol section 22.4 mark 13: no text in this phase claims an operator safety case.

Section 11.1 of the design brief is explicit. The read-only posture reduces the operational risk
surface and preserves human decision authority, and it does **not** satisfy a formal offshore
safety case, which is a far broader thing involving hazard identification, risk assessment,
safety-critical elements and a regulator. A portfolio project that implied otherwise would be
making the exact kind of overclaim this project exists to avoid.

**The gate matches claim shapes, not the bare phrase.** Section 22.4 mark 13 contains the words
"operator safety case" in the course of forbidding the claim, and so does this module. A gate on
the phrase alone would fire on its own prohibition and would be removed within a week, which is
how a check becomes a check nobody runs. What is forbidden is a sentence asserting the system
satisfies, meets, constitutes or is certified against one.

Two other overclaims are included for the same reason: a system kept outside the control loop has
no operational clearance, and nothing here carries anyone's certification.

Like the markup-sink gate, this one has no exception list, which means the project's own prose has
to be written around it. That cost is real and it is the point: the first run flagged a sentence in
this very docstring, because the negative lookbehind sees a quotation mark rather than the "not"
in front of it. The sentence was reworded. An exception list would have been easier and would have
been the beginning of a gate that no longer fires.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Final, NamedTuple

#: Claim shapes, as patterns. Each is a sentence fragment that asserts a status this project does
#: not have. The negated forms ("does not satisfy", "is not a") are excluded by the pattern, since
#: stating what the system is not is the opposite of the problem.
CLAIM_PATTERNS: Final[tuple[tuple[str, str], ...]] = (
    (
        "safety_case_satisfied",
        r"(?<!not )\b(satisf\w+|meet\w*|fulfil\w*|constitut\w+)\s+(a|an|the)\s+"
        r"(formal\s+|offshore\s+|operator\s+)*safety\s+case",
    ),
    (
        "is_a_safety_case",
        r"\bis\s+(a|an|the)\s+(formal\s+|offshore\s+|operator\s+)*safety\s+case\b",
    ),
    ("safety_case_compliant", r"\bsafety[-\s]case[-\s](compliant|certified|approved)\b"),
    (
        "approved_for_operations",
        r"(?<!not )\b(approved|certified|cleared|qualified)\s+for\s+"
        r"(operational|offshore|production|field)\s+use\b",
    ),
    ("regulatory_approval", r"\b(regulator|authority)[-\s]approved\b"),
    (
        "in_the_control_loop",
        r"\b(controls|actuates|operates)\s+(the\s+)?(well|choke|platform|facility)\b",
    ),
)

#: What the gate reads: the protocol, the phase's own documents, the architecture decisions and
#: the README. Source files are included because a docstring is published text too.
DEFAULT_ROOTS: Final[tuple[Path, ...]] = (
    Path("docs"),
    Path("README.md"),
    Path("src/volve_ops"),
    Path("api"),
    Path("scripts"),
    Path("frontend/src"),
)

SCANNED_SUFFIXES: Final[frozenset[str]] = frozenset({".md", ".py", ".ts", ".tsx", ".js", ".json"})


class Claim(NamedTuple):
    file: str
    line: int
    pattern: str
    text: str


def scan(roots: Sequence[Path] = DEFAULT_ROOTS) -> tuple[Claim, ...]:
    """Every sentence in the project's published text that claims a status it does not have."""
    return tuple(_claims(roots))


def _files(roots: Sequence[Path]) -> Iterator[Path]:
    for root in roots:
        if root.is_file():
            yield root
        elif root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix in SCANNED_SUFFIXES:
                    if "__pycache__" in path.parts or "node_modules" in path.parts:
                        continue
                    yield path


def _claims(roots: Sequence[Path]) -> Iterator[Claim]:
    compiled = [(name, re.compile(pattern, re.IGNORECASE)) for name, pattern in CLAIM_PATTERNS]
    for path in _files(roots):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover - unreadable file
            continue
        for number, line in enumerate(content.splitlines(), start=1):
            for name, pattern in compiled:
                if pattern.search(line):
                    yield Claim(file=str(path), line=number, pattern=name, text=line.strip()[:160])


def files_scanned(roots: Sequence[Path] = DEFAULT_ROOTS) -> int:
    """How many files the gate read. A scan of nothing passes, so the count is the result."""
    return sum(1 for _ in _files(roots))
