"""Determinism tests for HimKavach plant simulation models.

Ensures that:
1. Exact same random seeds yield identical trajectories (weather, loads, plant states).
2. Different seeds produce distinct trajectories.
"""

from datetime import UTC, datetime

import numpy as np
from himkavach_core.contracts.station import (
    BatteryConfig,
    FuelConfig,
    GensetConfig,
    LoadTierConfig,
    SolarPVConfig,
    ThermalConfig,
    WindTurbineConfig,
)
from himkavach_twin.battery import BatteryModel
from himkavach_twin.fuel_tank import FuelTankModel
from himkavach_twin.genset import GensetModel
from himkavach_twin.loads import LoadModel, ThermalModel
from himkavach_twin.solar import SolarPVModel
from himkavach_twin.weather_synth import generate_synthetic_weather
from himkavach_twin.wind import WindTurbineModel


def run_full_simulation_day(seed: int) -> dict[str, list[float]]:
    """Run a 24-hour full plant simulation given a random seed."""
    rng = np.random.default_rng(seed)
    start_dt = datetime(2026, 1, 15, 0, 0, tzinfo=UTC)

    # Weather
    weather = generate_synthetic_weather(
        latitude=-70.7667,
        longitude=11.7333,
        start=start_dt,
        hours=24,
        rng=rng,
    )

    # Initialize components
    pv = SolarPVModel(
        SolarPVConfig(
            id="PV_1",
            peak_power_kw=80.0,
            tilt_deg=65.0,
            azimuth_deg=0.0,
            temp_coeff_per_c=-0.0038,
            snow_shed_temp_c=-2.0,
        ),
        latitude=-70.7667,
        longitude=11.7333,
    )

    wind = WindTurbineModel(
        WindTurbineConfig(
            id="WIND_1",
            rated_power_kw=100.0,
            cut_in_speed_m_s=3.0,
            rated_speed_m_s=12.0,
            cut_out_speed_m_s=25.0,
            restart_speed_m_s=20.0,
            restart_dwell_min=10,
            hub_height_m=25.0,
            icing_derate_factor=0.85,
        )
    )

    battery = BatteryModel(
        BatteryConfig(
            id="BESS_1",
            capacity_kwh=600.0,
            max_charge_kw=300.0,
            max_discharge_kw=300.0,
            charge_efficiency=0.96,
            discharge_efficiency=0.96,
            min_soc=0.10,
            max_soc=1.00,
            min_temp_c_for_charging=0.0,
            heater_power_kw=5.0,
            degradation_cost_per_kwh=0.05,
        ),
        initial_soc=0.60,
    )

    genset = GensetModel(
        GensetConfig(
            id="GEN_1",
            rated_power_kw=150.0,
            min_load_ratio=0.30,
            fuel_intercept_l_per_h_kw=0.08,
            fuel_slope_l_per_h_kw=0.25,
            min_uptime_min=60,
            min_downtime_min=30,
            ramp_rate_kw_per_min=30.0,
            start_cost_usd=15.0,
            cold_start_delay_min=15,
            heat_recovery_efficiency=0.35,
        )
    )

    fuel_tank = FuelTankModel(
        FuelConfig(
            tank_capacity_l=180000.0,
            initial_inventory_l=150000.0,
            days_to_resupply=300,
            contingency_days=45,
            fuel_unit_cost_usd_per_l=2.50,
        )
    )

    thermal = ThermalModel(
        ThermalConfig(
            building_heat_capacity_kwh_per_c=180.0,
            building_heat_loss_kw_per_c=4.0,
            min_temp_c=16.0,
            max_temp_c=24.0,
            setpoint_temp_c=20.0,
            aux_heater_max_kw=100.0,
            water_tank_capacity_l=12000.0,
            snow_melter_power_kw=30.0,
        ),
        initial_indoor_temp_c=20.0,
    )

    load_model = LoadModel(
        [
            LoadTierConfig(
                tier=0,
                name="T0",
                base_kw=40.0,
                peak_kw=45.0,
                ride_through_min=0,
                max_daily_shed_hours=0.0,
                voll_usd_per_kwh=10000.0,
            ),
            LoadTierConfig(
                tier=1,
                name="T1",
                base_kw=15.0,
                peak_kw=20.0,
                ride_through_min=30,
                max_daily_shed_hours=1.0,
                voll_usd_per_kwh=500.0,
            ),
            LoadTierConfig(
                tier=2,
                name="T2",
                base_kw=45.0,
                peak_kw=110.0,
                ride_through_min=120,
                max_daily_shed_hours=8.0,
                voll_usd_per_kwh=20.0,
            ),
            LoadTierConfig(
                tier=3,
                name="T3",
                base_kw=20.0,
                peak_kw=75.0,
                ride_through_min=720,
                max_daily_shed_hours=18.0,
                voll_usd_per_kwh=3.0,
            ),
        ],
        rng=rng,
    )

    records: dict[str, list[float]] = {
        "pv_kw": [],
        "wind_kw": [],
        "total_load_kw": [],
        "battery_soc": [],
        "genset_kw": [],
        "fuel_tank_l": [],
        "indoor_temp_c": [],
    }

    for _h, w in enumerate(weather):
        pv_res = pv.step(w, dt_hours=1.0)
        wind_res = wind.step(
            wind_speed_m_s=w.wind_speed_m_s,
            temperature_c=w.temperature_c,
            pressure_hpa=w.surface_pressure_hpa,
            is_icing=w.is_icing_risk,
            dt_hours=1.0,
        )
        loads = load_model.generate_loads(
            hour_of_day=w.timestamp.hour,
            day_of_year=w.timestamp.timetuple().tm_yday,
            ambient_temp_c=w.temperature_c,
            wind_speed_m_s=w.wind_speed_m_s,
        )
        tot_load = sum(loads.values())

        # Simple baseline dispatch: renewables first, then battery, then genset
        re_power = pv_res["power_kw"] + wind_res["power_kw"]
        net_demand = tot_load - re_power

        if net_demand < 0:
            # Charge battery
            bat_setpoint = max(net_demand, -200.0)
            gen_target = False
            gen_setpoint = 0.0
        else:
            # Discharge battery up to 100 kW, remainder to genset
            bat_setpoint = min(net_demand, 100.0)
            unmet = net_demand - bat_setpoint
            if unmet > 30.0:
                gen_target = True
                gen_setpoint = unmet
            else:
                gen_target = False
                gen_setpoint = 0.0

        bat_res = battery.step(bat_setpoint, ambient_temp_c=w.temperature_c, dt_hours=1.0)
        gen_res = genset.step(
            gen_target, gen_setpoint, ambient_temp_c=w.temperature_c, dt_hours=1.0
        )
        tank_res = fuel_tank.step(gen_res["fuel_consumed_l"], dt_hours=1.0)
        therm_res = thermal.step(
            ambient_temp_c=w.temperature_c,
            wind_speed_m_s=w.wind_speed_m_s,
            waste_heat_kw=gen_res["waste_heat_kw"],
            aux_heating_kw=10.0,
            internal_gains_kw=5.0,
            dt_hours=1.0,
        )

        records["pv_kw"].append(pv_res["power_kw"])
        records["wind_kw"].append(wind_res["power_kw"])
        records["total_load_kw"].append(tot_load)
        records["battery_soc"].append(bat_res["soc"])
        records["genset_kw"].append(gen_res["power_kw"])
        records["fuel_tank_l"].append(tank_res["volume_l"])
        records["indoor_temp_c"].append(therm_res["indoor_temp_c"])

    return records


class TestSimulationDeterminism:
    def test_identical_seed_identical_trajectory(self):
        """Exact same random seed produces bitwise/float-identical simulation outputs."""
        sim1 = run_full_simulation_day(seed=9999)
        sim2 = run_full_simulation_day(seed=9999)

        for key in sim1:
            np.testing.assert_allclose(
                sim1[key],
                sim2[key],
                rtol=1e-12,
                atol=1e-12,
                err_msg=f"Trajectory mismatch for key {key}",
            )

    def test_different_seed_different_trajectory(self):
        """Different seeds produce distinct weather, load, and generation outputs."""
        sim1 = run_full_simulation_day(seed=1111)
        sim2 = run_full_simulation_day(seed=2222)

        # Weather and load paths should differ
        assert not np.allclose(sim1["total_load_kw"], sim2["total_load_kw"])
        assert not np.allclose(sim1["pv_kw"], sim2["pv_kw"])
        assert not np.allclose(sim1["wind_kw"], sim2["wind_kw"])
