"""Well name canonicalisation, which section 6 requires to be total."""

from __future__ import annotations

import pytest

from volve_ops.domain.well_naming import (
    UnresolvedWellName,
    canonical,
    canonical_from_ddr_token,
    is_canonical,
    well_of,
)


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("15_9_F_12", "15/9-F-12"),
        ("15_9_F_1_C", "15/9-F-1 C"),
        ("15_9_F_15_D", "15/9-F-15 D"),
        ("15_9_F_11_T2", "15/9-F-11 T2"),
        ("15_9_19_A", "15/9-19 A"),
        ("15_9_19_BT2", "15/9-19 BT2"),
    ],
)
def test_drilling_report_tokens_resolve(token: str, expected: str) -> None:
    assert canonical_from_ddr_token(token) == expected


def test_the_two_sources_meet_on_the_same_canonical_name() -> None:
    """The join the whole activity test depends on."""
    assert canonical_from_ddr_token("15_9_F_1_C") == canonical("15/9-F-1 C")
    assert canonical_from_ddr_token("15_9_F_15_D") == canonical("15/9-F-15 D")


@pytest.mark.parametrize(
    ("wellbore", "well"),
    [
        ("15/9-F-1 C", "15/9-F-1"),
        ("15/9-F-1 B", "15/9-F-1"),
        ("15/9-F-12", "15/9-F-12"),
        ("15/9-19 A", "15/9-19"),
    ],
)
def test_sidetracks_collapse_to_their_well(wellbore: str, well: str) -> None:
    assert well_of(wellbore) == well


def test_production_names_are_already_canonical() -> None:
    for name in ("15/9-F-1 C", "15/9-F-11", "15/9-F-15 D", "15/9-F-4"):
        assert is_canonical(name)
        assert canonical(name) == name


def test_an_unrecognised_name_raises_rather_than_passing_through() -> None:
    """Passing one through is how two spellings of one wellbore become two wells."""
    with pytest.raises(UnresolvedWellName):
        canonical("Norway-Statoil-NO 15_$47$_9-F-1 C")
    with pytest.raises(UnresolvedWellName):
        canonical("the F-12 well")
    with pytest.raises(UnresolvedWellName):
        canonical_from_ddr_token("nonsense")
