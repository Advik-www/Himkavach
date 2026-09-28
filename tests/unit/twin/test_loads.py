"""Unit tests for the tiered loads, building thermal model, and snow-melt tank."""

import numpy as np
import pytest
from himkavach_core.contracts.station import LoadTierConfig, ThermalConfig
from himkavach_twin.loads import LoadModel, SnowMeltTankModel, ThermalModel


@pytest.fixture
def tier_configs() -> list[LoadTierConfig]:
    return [
        LoadTierConfig(
            tier=0,
            name="Life Support",
            base_kw=40.0,
            peak_kw=45.0,
            ride_through_min=0,
            max_daily_shed_hours=0.0,
            voll_usd_per_kwh=10000.0,
        ),
        LoadTierConfig(
            tier=1,
            name="Science",
            base_kw=15.0,
            peak_kw=20.0,
            ride_through_min=30,
            max_daily_shed_hours=1.0,
            voll_usd_per_kwh=500.0,
        ),
        LoadTierConfig(
            tier=2,
            name="Comfort & Galley",
            base_kw=45.0,
            peak_kw=110.0,
            ride_through_min=120,
            max_daily_shed_hours=8.0,
            voll_usd_per_kwh=20.0,
        ),
        LoadTierConfig(
            tier=3,
            name="Deferrable Snow Melt",
            base_kw=20.0,
            peak_kw=75.0,
            ride_through_min=720,
            max_daily_shed_hours=18.0,
            voll_usd_per_kwh=3.0,
        ),
    ]


@pytest.fixture
def thermal_config() -> ThermalConfig:
    return ThermalConfig(
        building_heat_capacity_kwh_per_c=180.0,
        building_heat_loss_kw_per_c=4.0,
        min_temp_c=16.0,
        max_temp_c=24.0,
        setpoint_temp_c=20.0,
        aux_heater_max_kw=100.0,
        water_tank_capacity_l=12000.0,
        snow_melter_power_kw=30.0,
    )


class TestLoadModel:
    def test_load_bounds(self, tier_configs: list[LoadTierConfig]):
        """All tiers produce load within [0, peak_kw]."""
        rng = np.random.default_rng(42)
        model = LoadModel(tier_configs, rng)

        for hour in range(24):
            loads = model.generate_loads(
                hour_of_day=hour,
                day_of_year=150,
                ambient_temp_c=-20.0,
                wind_speed_m_s=8.0,
            )
            for tier, kw in loads.items():
                cfg = model.tier_configs[tier]
                assert 0.0 <= kw <= cfg.peak_kw

    def test_tier0_extreme_cold_increase(self, tier_configs: list[LoadTierConfig]):
        """Tier 0 life support increases slightly below -30°C."""
        # Fix rng seed to compare mean load
        rng1 = np.random.default_rng(123)
        model1 = LoadModel(tier_configs, rng1)
        loads_normal = [
            model1.generate_loads(12, 180, ambient_temp_c=-10.0, wind_speed_m_s=5.0)[0]
            for _ in range(50)
        ]

        rng2 = np.random.default_rng(123)
        model2 = LoadModel(tier_configs, rng2)
        loads_extreme = [
            model2.generate_loads(12, 180, ambient_temp_c=-50.0, wind_speed_m_s=5.0)[0]
            for _ in range(50)
        ]

        assert np.mean(loads_extreme) > np.mean(loads_normal)

    def test_tier2_meal_peaks(self, tier_configs: list[LoadTierConfig]):
        """Tier 2 comfort load is higher during meal hours (e.g. 12:00) than night hours (e.g. 03:00)."""
        rng = np.random.default_rng(42)
        model = LoadModel(tier_configs, rng)

        meal_loads = [
            model.generate_loads(
                hour_of_day=12, day_of_year=50, ambient_temp_c=-10.0, wind_speed_m_s=5.0
            )[2]
            for _ in range(50)
        ]
        night_loads = [
            model.generate_loads(
                hour_of_day=3, day_of_year=50, ambient_temp_c=-10.0, wind_speed_m_s=5.0
            )[2]
            for _ in range(50)
        ]

        assert np.mean(meal_loads) > np.mean(night_loads)


class TestThermalModel:
    def test_thermal_rc_cooling_without_heat(self, thermal_config: ThermalConfig):
        """Without heating input, indoor temperature decays toward ambient."""
        model = ThermalModel(thermal_config, initial_indoor_temp_c=20.0)
        res = model.step(
            ambient_temp_c=-30.0,
            wind_speed_m_s=5.0,
            waste_heat_kw=0.0,
            aux_heating_kw=0.0,
            internal_gains_kw=0.0,
            dt_hours=1.0,
        )
        assert res["indoor_temp_c"] < 20.0
        assert res["heat_loss_kw"] > 0.0

    def test_wind_chill_accelerates_cooling(self, thermal_config: ThermalConfig):
        """Higher wind speed increases UA conductance and accelerates heat loss."""
        model_calm = ThermalModel(thermal_config, initial_indoor_temp_c=20.0)
        res_calm = model_calm.step(
            ambient_temp_c=-20.0,
            wind_speed_m_s=0.0,
            waste_heat_kw=0.0,
            aux_heating_kw=0.0,
            internal_gains_kw=0.0,
            dt_hours=1.0,
        )

        model_windy = ThermalModel(thermal_config, initial_indoor_temp_c=20.0)
        res_windy = model_windy.step(
            ambient_temp_c=-20.0,
            wind_speed_m_s=25.0,  # strong wind
            waste_heat_kw=0.0,
            aux_heating_kw=0.0,
            internal_gains_kw=0.0,
            dt_hours=1.0,
        )

        assert res_windy["heat_loss_kw"] > res_calm["heat_loss_kw"]
        assert res_windy["indoor_temp_c"] < res_calm["indoor_temp_c"]

    def test_heating_equilibrium(self, thermal_config: ThermalConfig):
        """When heating exactly matches heat loss, indoor temperature remains constant."""
        model = ThermalModel(thermal_config, initial_indoor_temp_c=20.0)
        # UA at 0 wind is 4.0 kW/°C. Delta T = 20 - (-10) = 30°C. Heat loss = 120 kW.
        res = model.step(
            ambient_temp_c=-10.0,
            wind_speed_m_s=0.0,
            waste_heat_kw=60.0,
            aux_heating_kw=50.0,
            internal_gains_kw=10.0,  # total heating = 120 kW
            dt_hours=1.0,
        )
        assert pytest.approx(res["indoor_temp_c"], abs=1e-3) == 20.0
        assert pytest.approx(res["heat_loss_kw"], abs=1e-3) == 120.0


class TestSnowMeltTankModel:
    def test_snow_melting_produces_water(self):
        """Active snow melter consumes power and adds water."""
        tank = SnowMeltTankModel(capacity_l=1000.0, melter_power_kw=30.0, initial_level_l=500.0)

        # 1 hour with melter active: produces 30 kW * 1h / 0.115 kWh/L = ~260.87 L
        res = tank.step(melter_active=True, consumption_l_per_h=0.0, dt_hours=1.0)
        expected_produced = 30.0 / 0.115
        assert pytest.approx(res["water_produced_l"], rel=1e-3) == expected_produced
        assert pytest.approx(res["level_l"], rel=1e-3) == 500.0 + expected_produced
        assert res["power_consumed_kw"] == 30.0

    def test_consumption_reduces_level(self):
        """Water consumption reduces tank level."""
        tank = SnowMeltTankModel(capacity_l=1000.0, melter_power_kw=30.0, initial_level_l=500.0)
        res = tank.step(melter_active=False, consumption_l_per_h=50.0, dt_hours=2.0)
        assert res["level_l"] == 400.0
        assert res["water_consumed_l"] == 100.0

    def test_tank_capacity_ceiling(self):
        """Melter production cannot exceed tank capacity."""
        tank = SnowMeltTankModel(capacity_l=1000.0, melter_power_kw=30.0, initial_level_l=950.0)
        # Try to produce 260 L when only 50 L headroom remains
        res = tank.step(melter_active=True, consumption_l_per_h=0.0, dt_hours=1.0)
        assert res["level_l"] == 1000.0
        assert res["water_produced_l"] == 50.0
