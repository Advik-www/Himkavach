"""Unit tests for himkavach_core.units."""

import pytest
from himkavach_core.units import (
    DIESEL_CO2_KG_PER_L,
    DIESEL_LHV_KWH_PER_L,
    DIESEL_LHV_MJ_PER_L,
    air_density,
    celsius_to_kelvin,
    kelvin_to_celsius,
)


def test_temperature_conversions() -> None:
    assert celsius_to_kelvin(0.0) == pytest.approx(273.15, rel=1e-5)
    assert celsius_to_kelvin(-40.0) == pytest.approx(233.15, rel=1e-5)
    assert kelvin_to_celsius(273.15) == pytest.approx(0.0, abs=1e-5)
    assert kelvin_to_celsius(233.15) == pytest.approx(-40.0, abs=1e-5)


def test_air_density_sea_level() -> None:
    # At standard sea-level (15°C = 288.15K, 1013.25 hPa), density ~ 1.225 kg/m^3
    rho = air_density(15.0, 1013.25)
    assert rho == pytest.approx(1.225, rel=1e-2)

    # In extreme cold (-40°C, 985 hPa), air is significantly denser
    rho_cold = air_density(-40.0, 985.0)
    assert rho_cold > 1.40  # denser cold air boosts wind turbine aerodynamic lift
    assert rho_cold < 1.55


def test_diesel_constants() -> None:
    # Check physical plausibility of fuel properties
    assert 34.0 < DIESEL_LHV_MJ_PER_L < 38.0
    assert 9.0 < DIESEL_LHV_KWH_PER_L < 11.0
    assert 2.5 < DIESEL_CO2_KG_PER_L < 2.8
