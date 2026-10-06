"""Well and wellbore name canonicalisation.

docs/eval_protocol.md section 6 requires this to be total: every name in every source resolves
to one canonical entity, or is quarantined. A silently unmatched name is a failure, not a
warning, because an unmatched drilling report is a window that looks activity-free when it is
not.

The sources disagree on spelling. The production workbook writes `15/9-F-1 C`. The daily
drilling reports are filed as `15_9_F_1_C`, with underscores standing in for both the hyphen
and the space. Both describe the same wellbore.

Canonical form follows the regulator's convention, which the production workbook already uses:
field, then the well, then an optional wellbore suffix. `15/9-F-1 C` is wellbore C of well
15/9-F-1; `15/9-19 A` is wellbore A of exploration well 15/9-19.
"""

from __future__ import annotations

import re
from typing import Final

FIELD_PREFIX: Final[str] = "15/9-"

# 15_9_F_1_C  ->  field 15/9, well F-1, wellbore C
# 15_9_19_A   ->  field 15/9, well 19,  wellbore A
_DDR_TOKEN = re.compile(r"^(\d+)_(\d+)_(.+)$")
_CANONICAL = re.compile(r"^\d+/\d+-[A-Z]?-?\d+[A-Z]?(?: [A-Z]+\d*)?$")


class UnresolvedWellName(ValueError):
    """A name could not be resolved to a canonical wellbore.

    Raised rather than returning the input unchanged. Passing an unrecognised name through is
    how two spellings of one wellbore become two wells in a join.
    """


def canonical_from_ddr_token(token: str) -> str:
    """Resolve a drilling-report filename token such as `15_9_F_15_D`.

    The token is the filename with the date suffix stripped. Underscores separate every part,
    so the structure has to be recovered rather than string-replaced: the separator between a
    well and its wellbore is a space, while the one inside a platform well name is a hyphen.
    """
    match = _DDR_TOKEN.match(token.strip())
    if not match:
        raise UnresolvedWellName(f"not a recognised drilling-report well token: {token!r}")

    quadrant, block, rest = match.groups()
    parts = rest.split("_")

    if parts[0].isalpha() and len(parts) >= 2:
        # A platform well: the letter and the number are one name joined by a hyphen.
        well = f"{parts[0]}-{parts[1]}"
        wellbore = parts[2:]
    else:
        # An exploration well: the number is the name on its own.
        well = parts[0]
        wellbore = parts[1:]

    name = f"{quadrant}/{block}-{well}"
    if wellbore:
        name = f"{name} {' '.join(wellbore)}"
    return name


def is_canonical(name: str) -> bool:
    """Whether a name is already in canonical form."""
    return bool(_CANONICAL.match(name.strip()))


def canonical(name: str) -> str:
    """Resolve any supported spelling. Raises UnresolvedWellName rather than guessing."""
    stripped = name.strip()
    if is_canonical(stripped):
        return stripped
    if _DDR_TOKEN.match(stripped) and "_" in stripped:
        return canonical_from_ddr_token(stripped)
    raise UnresolvedWellName(f"cannot resolve {name!r} to a canonical wellbore")


def well_of(wellbore: str) -> str:
    """The well a wellbore belongs to, with the wellbore suffix removed.

    `15/9-F-1 C` and `15/9-F-1 B` are both wellbores of well `15/9-F-1`. Sidetracks count once
    wherever the protocol counts wells rather than wellbores.
    """
    return canonical(wellbore).split(" ", 1)[0]
