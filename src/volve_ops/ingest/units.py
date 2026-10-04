"""Unit conversion at the ingest boundary.

docs/eval_protocol.md fixes Sm3 as the canonical volume unit for every liquid and gas
quantity in the project, with conversion happening once, here, before anything downstream
sees a number.

Sm3 here means a volume at the metric standard reference condition, 15 degrees Celsius and
1.01325 bar. That matters for gas and barely at all for liquids, which is why conversion is
split by fluid below.

An unknown unit raises, and so does a gas volume stated at unknown conditions. Guessing is
how a barrel-per-day series silently becomes a cubic-metre-per-day series, a factor of about
6.29 in every shortfall downstream that nobody would question.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

CANONICAL_VOLUME_UNIT: Final[str] = "Sm3"
CANONICAL_TIME_UNIT: Final[str] = "h"


class Fluid(StrEnum):
    """Which fluid a volume describes. Required, because the conversions differ."""

    LIQUID = "liquid"
    GAS = "gas"


class UnknownUnitError(ValueError):
    """A source unit has no registered conversion for this fluid, so it is not usable."""


# Multiply a source value by this to get Sm3.
#
# For liquids, a cubic metre and a standard cubic metre differ only by thermal expansion
# between the measurement and reference temperature, well under a percent, so m3 is accepted
# as Sm3 and the approximation is recorded here.
_LIQUID_TO_SM3: Final[dict[str, float]] = {
    "sm3": 1.0,
    "m3": 1.0,
    "bbl": 0.158987294928,
    "stb": 0.158987294928,
}

# For gas, an actual-conditions volume is not comparable to a standard one: the same gas at
# line or reservoir conditions occupies one to two orders of magnitude less space. So bare
# m3 and Am3 are refused for gas rather than passed through, and a caller holding such a
# series has to convert it with the conditions it was measured at.
#
# scf and mscf convert by exact geometry (1 ft3 = 0.028316846592 m3). The residual error is
# the difference in reference condition, since a standard cubic foot is defined at 60 F and
# roughly 14.7 psia rather than 15 C and 1.01325 bar, worth a few tenths of a percent. The
# twelve-digit constant describes the geometry, not the accuracy.
_GAS_TO_SM3: Final[dict[str, float]] = {
    "sm3": 1.0,
    "scf": 0.028316846592,
    "mscf": 28.316846592,
}

_REFUSED_GAS_UNITS: Final[frozenset[str]] = frozenset({"m3", "am3", "acf", "rm3"})

_TIME_TO_HOURS: Final[dict[str, float]] = {
    "h": 1.0,
    "hr": 1.0,
    "hour": 1.0,
    "hours": 1.0,
    "min": 1.0 / 60.0,
    "d": 24.0,
    "day": 24.0,
}


def to_sm3(value: float, unit: str, *, fluid: Fluid) -> float:
    """Convert a volume to Sm3. The fluid is required; the tables differ.

    Raises UnknownUnitError for an unregistered unit, and for a gas volume stated at
    actual conditions, which cannot be converted without knowing those conditions.
    """
    key = unit.strip().lower()
    table = _LIQUID_TO_SM3 if fluid is Fluid.LIQUID else _GAS_TO_SM3

    if fluid is Fluid.GAS and key in _REFUSED_GAS_UNITS:
        raise UnknownUnitError(
            f"gas volume in {unit!r} is at actual conditions, not standard conditions; "
            "convert it with the pressure and temperature it was measured at before ingest"
        )

    factor = table.get(key)
    if factor is None:
        raise UnknownUnitError(
            f"no conversion registered for {fluid.value} volume unit {unit!r}; "
            f"known units: {sorted(table)}"
        )
    return value * factor


def to_hours(value: float, unit: str) -> float:
    """Convert a duration to hours. Raises UnknownUnitError for an unregistered unit."""
    key = unit.strip().lower()
    factor = _TIME_TO_HOURS.get(key)
    if factor is None:
        raise UnknownUnitError(
            f"no conversion registered for time unit {unit!r}; "
            f"known units: {sorted(_TIME_TO_HOURS)}"
        )
    return value * factor
