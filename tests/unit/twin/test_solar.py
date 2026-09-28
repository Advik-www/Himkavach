"""Unit tests for the Solar PV plant model."""

from datetime import UTC, datetime

import pytest
from himkavach_core.contracts.station import SolarPVConfig
from himkavach_core.contracts.weather import WeatherObs
from himkavach_twin.solar import SolarPVModel


@pytest.fixture
def pv_config() -> SolarPVConfig:
    return SolarPVConfig(
        id="PV_TEST",
        peak_power_kw=80.0,
        tilt_deg=65.0,
        azimuth_deg=0.0,  # North-facing in Southern hemisphere
        temp_coeff_per_c=-0.0038,
        snow_shed_temp_c=-2.0,
    )


@pytest.fixture
def solar_model(pv_config: SolarPVConfig) -> SolarPVModel:
    # Maitri Station coordinates ~70.8°S, 11.7°E
    return SolarPVModel(config=pv_config, latitude=-70.7667, longitude=11.7333)


def make_weather(
    dt: datetime,
    temp_c: float = -10.0,
    ghi: float = 600.0,
    dni: float = 500.0,
    dhi: float = 100.0,
    snowfall: float = 0.0,
) -> WeatherObs:
    return WeatherObs(
        timestamp=dt,
        temperature_c=temp_c,
        wind_speed_m_s=5.0,
        wind_direction_deg=90.0,
        wind_gust_m_s=8.0,
        surface_pressure_hpa=985.0,
        relative_humidity_pct=60.0,
        ghi_w_m2=ghi,
        dni_w_m2=dni,
        dhi_w_m2=dhi,
        snowfall_rate_mm_h=snowfall,
        pressure_tendency_3h_hpa=0.0,
        temp_tendency_3h_c=0.0,
        is_icing_risk=False,
        storm_regime="CALM_NORMAL",
    )


class TestSolarPVModel:
    def test_night_zero_irradiance_produces_zero_power(self, solar_model: SolarPVModel):
        """During polar night (or sun below horizon), power must be zero."""
        # Midnight in winter: July 1 at 70°S is complete polar night
        dt = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
        w = make_weather(dt, ghi=0.0, dni=0.0, dhi=0.0)
        res = solar_model.step(w, dt_hours=1.0)
        assert res["power_kw"] == 0.0
        assert res["poa_irradiance_w_m2"] == 0.0

    def test_snow_accumulation_reduces_power(self, solar_model: SolarPVModel):
        """Snowfall accumulation increases snow cover and decreases power."""
        # Polar summer noon (Jan 1) with sun up
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        w_clear = make_weather(dt, snowfall=0.0)

        # Baseline step with clean panels
        solar_model.reset(snow_cover=0.0)
        res_clean = solar_model.step(w_clear, dt_hours=1.0)
        assert res_clean["power_kw"] > 0.0
        assert res_clean["snow_cover_ratio"] == 0.0

        # Step with heavy snowfall
        w_snow = make_weather(dt, snowfall=5.0)
        res_snow = solar_model.step(w_snow, dt_hours=1.0)
        assert res_snow["snow_cover_ratio"] > 0.0
        assert res_snow["power_kw"] < res_clean["power_kw"]

    def test_complete_snow_cover_yields_zero_power(self, solar_model: SolarPVModel):
        """When snow cover is 100%, PV produces 0 power."""
        solar_model.snow_cover = 1.0
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        # Heavy snowfall keeps snow cover saturated at 1.0 despite solar shedding
        w = make_weather(dt, snowfall=20.0)
        res = solar_model.step(w, dt_hours=1.0)
        assert res["snow_cover_ratio"] == 1.0
        assert res["power_kw"] == 0.0

    def test_snow_shedding_above_temperature_threshold(self, solar_model: SolarPVModel):
        """Temperatures above snow_shed_temp_c shed snow cover."""
        solar_model.snow_cover = 0.5
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        # Temp above -2.0°C shed threshold
        w_warm = make_weather(dt, temp_c=3.0, snowfall=0.0)
        solar_model.step(w_warm, dt_hours=2.0)
        assert solar_model.snow_cover < 0.5

    def test_cold_temperature_efficiency_boost(self, solar_model: SolarPVModel):
        """Cold cell temperature boosts PV efficiency (negative temperature coefficient)."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        solar_model.reset(snow_cover=0.0)

        # Cold step: -30°C
        w_cold = make_weather(dt, temp_c=-30.0)
        res_cold = solar_model.step(w_cold, dt_hours=1.0)

        # Warm step: +15°C
        solar_model.reset(snow_cover=0.0)
        w_warm = make_weather(dt, temp_c=15.0)
        res_warm = solar_model.step(w_warm, dt_hours=1.0)

        # Cold temperature factor should be higher than warm temperature factor
        assert res_cold["temp_derate_factor"] > res_warm["temp_derate_factor"]
        assert res_cold["power_kw"] > res_warm["power_kw"]

    def test_reset(self, solar_model: SolarPVModel):
        """Reset clears snow cover."""
        solar_model.snow_cover = 0.8
        solar_model.reset(snow_cover=0.0)
        assert solar_model.snow_cover == 0.0
