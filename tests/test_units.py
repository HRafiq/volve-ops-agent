"""Unit conversion at the ingest boundary."""

from __future__ import annotations

import pytest

from volve_ops.ingest.units import Fluid, UnknownUnitError, to_hours, to_sm3

BBL_IN_SM3 = 0.158987294928
FT3_IN_SM3 = 0.028316846592


class TestLiquids:
    def test_sm3_and_m3_pass_through(self) -> None:
        assert to_sm3(1234.5, "Sm3", fluid=Fluid.LIQUID) == 1234.5
        assert to_sm3(1234.5, "m3", fluid=Fluid.LIQUID) == 1234.5

    def test_barrels_convert_exactly(self) -> None:
        assert to_sm3(1000.0, "bbl", fluid=Fluid.LIQUID) == pytest.approx(BBL_IN_SM3 * 1000)
        assert to_sm3(1000.0, "STB", fluid=Fluid.LIQUID) == pytest.approx(BBL_IN_SM3 * 1000)

    def test_lookup_ignores_case_and_surrounding_space(self) -> None:
        assert to_sm3(1.0, "  BBL ", fluid=Fluid.LIQUID) == pytest.approx(BBL_IN_SM3)

    def test_a_gas_unit_is_not_available_to_a_liquid(self) -> None:
        with pytest.raises(UnknownUnitError, match="liquid volume unit"):
            to_sm3(1.0, "mscf", fluid=Fluid.LIQUID)


class TestGas:
    def test_standard_cubic_feet_convert_by_geometry(self) -> None:
        assert to_sm3(1000.0, "scf", fluid=Fluid.GAS) == pytest.approx(FT3_IN_SM3 * 1000)
        assert to_sm3(1.0, "mscf", fluid=Fluid.GAS) == pytest.approx(FT3_IN_SM3 * 1000)

    @pytest.mark.parametrize("unit", ["m3", "Am3", "rm3", "acf"])
    def test_actual_condition_gas_volumes_are_refused_rather_than_assumed(self, unit: str) -> None:
        """The same gas at line conditions occupies orders of magnitude less space."""
        with pytest.raises(UnknownUnitError, match="actual conditions"):
            to_sm3(1.0, unit, fluid=Fluid.GAS)

    def test_sm3_passes_through(self) -> None:
        assert to_sm3(900.0, "sm3", fluid=Fluid.GAS) == 900.0


def test_unknown_volume_unit_raises_rather_than_guessing() -> None:
    with pytest.raises(UnknownUnitError, match="volume unit"):
        to_sm3(1.0, "kilolitres", fluid=Fluid.LIQUID)


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [(24.0, "h", 24.0), (1.0, "hr", 1.0), (90.0, "min", 1.5), (1.0, "d", 24.0), (2.0, "day", 48.0)],
)
def test_time_conversions(value: float, unit: str, expected: float) -> None:
    assert to_hours(value, unit) == pytest.approx(expected)


def test_unknown_time_unit_raises() -> None:
    with pytest.raises(UnknownUnitError, match="time unit"):
        to_hours(1.0, "fortnights")
