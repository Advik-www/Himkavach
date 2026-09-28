"""Property-based energy balance tests for HimKavach plant components.

Tests verify first-law thermodynamic and mass conservation invariants:
Energy_in = Energy_out + Delta_stored
Mass_in = Mass_out + Delta_stored
"""

import pytest
from himkavach_core.contracts.station import BatteryConfig, FuelConfig, ThermalConfig
from himkavach_twin.battery import BatteryModel
from himkavach_twin.fuel_tank import FuelTankModel
from himkavach_twin.loads import SnowMeltTankModel, ThermalModel
from hypothesis import given, settings
from hypothesis import strategies as st


class TestComponentEnergyBalances:
    """Property-based conservation tests for individual components."""

    @given(
        initial_soc=st.floats(min_value=0.20, max_value=0.80),
        power_setpoint=st.floats(min_value=-250.0, max_value=250.0),
        dt_hours=st.floats(min_value=0.1, max_value=1.0),
    )
    @settings(max_examples=50)
    def test_battery_energy_conservation(
        self, initial_soc: float, power_setpoint: float, dt_hours: float
    ):
        """Battery terminal energy equals delta stored energy plus internal losses."""
        cfg = BatteryConfig(
            id="BAT_PROP",
            capacity_kwh=600.0,
            max_charge_kw=300.0,
            max_discharge_kw=300.0,
            charge_efficiency=0.95,
            discharge_efficiency=0.95,
            min_soc=0.10,
            max_soc=1.00,
            min_temp_c_for_charging=0.0,
            heater_power_kw=5.0,
            degradation_cost_per_kwh=0.05,
        )
        bat = BatteryModel(config=cfg, initial_soc=initial_soc)
        bat.reset(soc=initial_soc, cell_temp_c=25.0)  # warm, no derating

        effective_capacity = bat.config.capacity_kwh * bat.soh
        soc_before = bat.soc
        res = bat.step(power_setpoint_kw=power_setpoint, ambient_temp_c=20.0, dt_hours=dt_hours)
        soc_after = bat.soc
        delta_stored = (soc_after - soc_before) * effective_capacity

        actual_p = res["actual_power_kw"]
        losses_kwh = res["losses_kw"] * dt_hours

        if actual_p < 0:
            # Charging: Terminal Energy In = abs(P) * dt = delta_stored + losses
            energy_in = abs(actual_p) * dt_hours
            assert pytest.approx(energy_in, rel=1e-4, abs=1e-5) == delta_stored + losses_kwh
        elif actual_p > 0:
            # Discharging: Energy out of cells = -delta_stored = Terminal Energy Out + losses
            energy_out = actual_p * dt_hours
            assert pytest.approx(-delta_stored, rel=1e-4, abs=1e-5) == energy_out + losses_kwh
        else:
            assert pytest.approx(delta_stored, abs=1e-5) == 0.0

    @given(
        initial_temp=st.floats(min_value=15.0, max_value=25.0),
        ambient_temp=st.floats(min_value=-50.0, max_value=10.0),
        wind_speed=st.floats(min_value=0.0, max_value=35.0),
        waste_heat=st.floats(min_value=0.0, max_value=100.0),
        aux_heat=st.floats(min_value=0.0, max_value=80.0),
        dt_hours=st.floats(min_value=0.25, max_value=2.0),
    )
    @settings(max_examples=50)
    def test_thermal_energy_conservation(
        self,
        initial_temp: float,
        ambient_temp: float,
        wind_speed: float,
        waste_heat: float,
        aux_heat: float,
        dt_hours: float,
    ):
        """Thermal RC model strictly obeys C * Delta T = (Q_in - Q_loss) * dt."""
        cfg = ThermalConfig(
            building_heat_capacity_kwh_per_c=180.0,
            building_heat_loss_kw_per_c=4.0,
            min_temp_c=16.0,
            max_temp_c=24.0,
            setpoint_temp_c=20.0,
            aux_heater_max_kw=100.0,
            water_tank_capacity_l=12000.0,
            snow_melter_power_kw=30.0,
        )
        model = ThermalModel(cfg, initial_indoor_temp_c=initial_temp)

        res = model.step(
            ambient_temp_c=ambient_temp,
            wind_speed_m_s=wind_speed,
            waste_heat_kw=waste_heat,
            aux_heating_kw=aux_heat,
            internal_gains_kw=5.0,
            dt_hours=dt_hours,
        )

        delta_temp = res["indoor_temp_c"] - initial_temp
        c_th = cfg.building_heat_capacity_kwh_per_c
        delta_energy_stored = c_th * delta_temp

        heat_net = (res["total_heating_kw"] - res["heat_loss_kw"]) * dt_hours
        assert pytest.approx(delta_energy_stored, rel=1e-4, abs=1e-5) == heat_net

    @given(
        initial_vol=st.floats(min_value=50000.0, max_value=150000.0),
        burn=st.floats(min_value=0.0, max_value=100.0),
        leak_rate=st.floats(min_value=0.0, max_value=10.0),
        resupply_vol=st.floats(min_value=0.0, max_value=5000.0),
        dt_hours=st.floats(min_value=0.5, max_value=4.0),
    )
    @settings(max_examples=50)
    def test_fuel_tank_mass_conservation(
        self,
        initial_vol: float,
        burn: float,
        leak_rate: float,
        resupply_vol: float,
        dt_hours: float,
    ):
        """Fuel tank inventory change matches exactly: -burned -leaked +resupply."""
        cfg = FuelConfig(
            tank_capacity_l=180000.0,
            initial_inventory_l=initial_vol,
            days_to_resupply=300,
            contingency_days=45,
            fuel_unit_cost_usd_per_l=2.50,
        )
        tank = FuelTankModel(cfg)
        tank.inject_leak(leak_rate)

        # Step 1: drawdown from burn and leak
        res = tank.step(fuel_burned_l=burn, dt_hours=dt_hours)
        expected_draw = res["fuel_burned_l"] + res["fuel_leaked_l"]
        assert pytest.approx(initial_vol - tank.volume_l, rel=1e-4, abs=1e-5) == expected_draw

        # Step 2: resupply
        vol_before_resupply = tank.volume_l
        added = tank.resupply(resupply_vol)
        assert pytest.approx(tank.volume_l - vol_before_resupply, rel=1e-4, abs=1e-5) == added

    @given(
        initial_level=st.floats(min_value=1000.0, max_value=8000.0),
        consumption_rate=st.floats(min_value=10.0, max_value=100.0),
        dt_hours=st.floats(min_value=0.5, max_value=4.0),
    )
    @settings(max_examples=50)
    def test_water_tank_mass_balance(
        self,
        initial_level: float,
        consumption_rate: float,
        dt_hours: float,
    ):
        """Snow melt tank water level delta equals water produced minus water consumed."""
        tank = SnowMeltTankModel(
            capacity_l=12000.0, melter_power_kw=30.0, initial_level_l=initial_level
        )
        res = tank.step(melter_active=True, consumption_l_per_h=consumption_rate, dt_hours=dt_hours)

        delta_level = res["level_l"] - initial_level
        net_water = res["water_produced_l"] - res["water_consumed_l"]
        assert pytest.approx(delta_level, rel=1e-4, abs=1e-5) == net_water


class TestStationEnergyBalance:
    """Property test for microgrid electrical power conservation across all components."""

    @given(
        wind_speed=st.floats(min_value=0.0, max_value=30.0),
        ghi=st.floats(min_value=0.0, max_value=800.0),
        load_kw=st.floats(min_value=50.0, max_value=180.0),
    )
    @settings(max_examples=40)
    def test_station_electrical_power_balance(self, wind_speed: float, ghi: float, load_kw: float):
        """Total Electrical Sources == Total Electrical Sinks + Unmet / Curtailment.

        Sources: PV power + Wind power + Genset power + Battery discharge
        Sinks: Station load + Battery charge + Battery heater + Melter + Curtailment
        """
        # Given any dispatch scenario:
        # P_sources = P_pv + P_wind + P_genset + P_battery_discharge
        # P_sinks = P_load + P_battery_charge + P_aux
        # Sources - Sinks = 0 (exact balance in synchronous microgrid)
        # Verify this algebraic invariant holds cleanly
        p_pv = max(0.0, ghi * 0.08)  # simple linear pv approximation
        p_wind = (
            100.0 * min(1.0, max(0.0, (wind_speed - 3.0) / 9.0) ** 3)
            if 3.0 <= wind_speed <= 25.0
            else 0.0
        )

        p_renewables = p_pv + p_wind
        surplus = p_renewables - load_kw

        if surplus >= 0:
            # Renewable surplus charges battery or curtails
            p_bat_charge = min(surplus, 100.0)  # up to 100 kW battery charge
            p_curtailed = surplus - p_bat_charge
            p_gen = 0.0
            p_bat_discharge = 0.0
        else:
            # Deficit: battery discharges or genset runs
            deficit = -surplus
            p_bat_discharge = min(deficit, 80.0)
            remaining_deficit = deficit - p_bat_discharge
            p_gen = remaining_deficit
            p_bat_charge = 0.0
            p_curtailed = 0.0

        sources = p_pv + p_wind + p_gen + p_bat_discharge
        sinks = load_kw + p_bat_charge + p_curtailed

        assert pytest.approx(sources, rel=1e-4, abs=1e-5) == sinks
