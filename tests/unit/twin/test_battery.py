"""Unit tests for the Battery Energy Storage System (BESS) model."""

import pytest
from himkavach_core.contracts.station import BatteryConfig
from himkavach_twin.battery import BatteryModel


@pytest.fixture
def battery_config() -> BatteryConfig:
    return BatteryConfig(
        id="BESS_TEST",
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
    )


@pytest.fixture
def battery_model(battery_config: BatteryConfig) -> BatteryModel:
    return BatteryModel(config=battery_config, initial_soc=0.50)


class TestBatteryModel:
    def test_cold_charge_lockout(self, battery_model: BatteryModel):
        """Battery refuses all charging when cell temperature is below min_temp_c_for_charging."""
        # Set cell temperature below 0.0°C (e.g. -5°C)
        battery_model.reset(soc=0.50, cell_temp_c=-5.0)

        # Attempt to charge at 150 kW (power_setpoint < 0)
        res = battery_model.step(power_setpoint_kw=-150.0, ambient_temp_c=-20.0, dt_hours=1.0)

        assert res["charge_derate"] == 0.0
        assert res["actual_power_kw"] == 0.0
        assert res["soc"] == 0.50  # SoC unchanged

    def test_warm_charging_permitted(self, battery_model: BatteryModel):
        """Charging proceeds normally when cells are warm (>0°C)."""
        battery_model.reset(soc=0.50, cell_temp_c=25.0)

        res = battery_model.step(power_setpoint_kw=-100.0, ambient_temp_c=20.0, dt_hours=1.0)
        assert res["actual_power_kw"] == -100.0
        assert res["soc"] > 0.50
        assert res["charge_derate"] == 1.0

    def test_discharge_derating_in_cold(self, battery_model: BatteryModel):
        """Discharge power is derated but not completely locked out in cold conditions."""
        # At -40°C, discharge derate is 0.3
        battery_model.reset(soc=0.80, cell_temp_c=-40.0)
        res_extreme = battery_model.step(
            power_setpoint_kw=300.0, ambient_temp_c=-40.0, dt_hours=0.25
        )
        assert res_extreme["discharge_derate"] == 0.3
        assert pytest.approx(res_extreme["actual_power_kw"]) == 300.0 * 0.3

        # At 25°C, discharge derate is 1.0
        battery_model.reset(soc=0.80, cell_temp_c=25.0)
        res_warm = battery_model.step(power_setpoint_kw=300.0, ambient_temp_c=20.0, dt_hours=0.25)
        assert res_warm["discharge_derate"] == 1.0
        assert pytest.approx(res_warm["actual_power_kw"]) == 300.0

    def test_heater_activates_below_threshold(self, battery_model: BatteryModel):
        """Battery enclosure heater activates when cell temperature drops below 5°C."""
        battery_model.reset(soc=0.50, cell_temp_c=2.0)
        res = battery_model.step(power_setpoint_kw=0.0, ambient_temp_c=-20.0, dt_hours=1.0)
        assert res["heater_power_kw"] == 5.0
        assert battery_model.heater_active

        battery_model.reset(soc=0.50, cell_temp_c=15.0)
        res = battery_model.step(power_setpoint_kw=0.0, ambient_temp_c=-20.0, dt_hours=1.0)
        assert res["heater_power_kw"] == 0.0
        assert not battery_model.heater_active

    def test_soc_min_and_max_bounds(self, battery_model: BatteryModel):
        """Battery clamps at min_soc and max_soc."""
        # 1. At min_soc, discharge produces 0
        battery_model.reset(soc=0.10, cell_temp_c=20.0)
        res = battery_model.step(power_setpoint_kw=100.0, ambient_temp_c=20.0, dt_hours=1.0)
        assert res["actual_power_kw"] == 0.0
        assert res["soc"] == 0.10

        # 2. At max_soc, charge produces 0
        battery_model.reset(soc=1.00, cell_temp_c=20.0)
        res = battery_model.step(power_setpoint_kw=-100.0, ambient_temp_c=20.0, dt_hours=1.0)
        assert res["actual_power_kw"] == 0.0
        assert res["soc"] == 1.00

    def test_cycle_degradation(self, battery_model: BatteryModel):
        """Throughput accumulates and SoH decreases with cycling."""
        battery_model.reset(soc=0.50, cell_temp_c=20.0)
        initial_soh = battery_model.soh

        # Discharge 200 kW for 1 hour
        battery_model.step(power_setpoint_kw=200.0, ambient_temp_c=20.0, dt_hours=1.0)
        assert battery_model.total_throughput_kwh > 0.0
        assert battery_model.equivalent_full_cycles > 0.0
        assert battery_model.soh < initial_soh

    def test_single_step_energy_balance(self, battery_model: BatteryModel):
        """Energy drawn/supplied matches delta stored energy plus losses."""
        # Charging: Terminal Energy = Delta Stored + Losses
        battery_model.reset(soc=0.50, cell_temp_c=20.0)
        c = battery_model.config.capacity_kwh
        eff_ch = battery_model.config.charge_efficiency

        res_ch = battery_model.step(power_setpoint_kw=-100.0, ambient_temp_c=20.0, dt_hours=1.0)
        delta_stored_ch = (res_ch["soc"] - 0.50) * c
        expected_energy_in = abs(res_ch["actual_power_kw"]) * 1.0
        assert pytest.approx(delta_stored_ch, rel=1e-3) == expected_energy_in * eff_ch

        # Discharging: Delta Stored = Terminal Energy / discharge_efficiency
        battery_model.reset(soc=0.50, cell_temp_c=20.0)
        eff_dis = battery_model.config.discharge_efficiency
        res_dis = battery_model.step(power_setpoint_kw=100.0, ambient_temp_c=20.0, dt_hours=1.0)
        delta_stored_dis = (0.50 - res_dis["soc"]) * c
        expected_energy_out = res_dis["actual_power_kw"] * 1.0
        assert pytest.approx(delta_stored_dis, rel=1e-3) == expected_energy_out / eff_dis
