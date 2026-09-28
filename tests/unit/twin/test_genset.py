"""Unit tests for the Diesel Generator (genset) model."""

import pytest
from himkavach_core.contracts.station import GensetConfig
from himkavach_core.units import DIESEL_LHV_KWH_PER_L
from himkavach_twin.genset import GensetModel


@pytest.fixture
def genset_config() -> GensetConfig:
    return GensetConfig(
        id="GEN_TEST",
        rated_power_kw=150.0,
        min_load_ratio=0.30,  # 45 kW min stable
        fuel_intercept_l_per_h_kw=0.08,  # a = 12.0 L/h
        fuel_slope_l_per_h_kw=0.25,  # b = 0.25 L/kWh
        min_uptime_min=60,
        min_downtime_min=30,
        ramp_rate_kw_per_min=30.0,
        start_cost_usd=15.0,
        cold_start_delay_min=15,
        heat_recovery_efficiency=0.35,
    )


@pytest.fixture
def genset_model(genset_config: GensetConfig) -> GensetModel:
    return GensetModel(config=genset_config)


class TestGensetModel:
    def test_fuel_curve_sample_points(self, genset_model: GensetModel):
        """Fuel consumption rate matches F = a*P_rated + b*P_output at sample points."""
        cfg = genset_model.config
        a_p_rated = cfg.fuel_intercept_l_per_h_kw * cfg.rated_power_kw  # 0.08 * 150 = 12.0 L/h
        b = cfg.fuel_slope_l_per_h_kw  # 0.25 L/kWh

        # 1. Offline -> 0 L/h
        assert genset_model.fuel_rate_l_per_h == 0.0
        res_off = genset_model.step(
            target_online=False, power_setpoint_kw=0.0, ambient_temp_c=-10.0
        )
        assert res_off["fuel_rate_l_per_h"] == 0.0

        # Start genset (let it warm up for 1 hour so warmup is complete)
        genset_model.step(
            target_online=True, power_setpoint_kw=45.0, ambient_temp_c=-10.0, dt_hours=1.0
        )
        assert genset_model.is_online

        # Sample point 1: Min stable load (45 kW)
        res_45 = genset_model.step(
            target_online=True, power_setpoint_kw=45.0, ambient_temp_c=-10.0, dt_hours=0.25
        )
        expected_f45 = a_p_rated + b * 45.0  # 12.0 + 11.25 = 23.25 L/h
        assert pytest.approx(res_45["fuel_rate_l_per_h"], rel=1e-3) == expected_f45

        # Sample point 2: Mid load (100 kW)
        res_100 = genset_model.step(
            target_online=True, power_setpoint_kw=100.0, ambient_temp_c=-10.0, dt_hours=0.25
        )
        expected_f100 = a_p_rated + b * 100.0  # 12.0 + 25.0 = 37.0 L/h
        assert pytest.approx(res_100["fuel_rate_l_per_h"], rel=1e-3) == expected_f100

        # Sample point 3: Rated load (150 kW)
        res_150 = genset_model.step(
            target_online=True, power_setpoint_kw=150.0, ambient_temp_c=-10.0, dt_hours=0.25
        )
        expected_f150 = a_p_rated + b * 150.0  # 12.0 + 37.5 = 49.5 L/h
        assert pytest.approx(res_150["fuel_rate_l_per_h"], rel=1e-3) == expected_f150

    def test_min_stable_load_enforced(self, genset_model: GensetModel):
        """Requesting load below min_stable_power_kw is clamped up to min stable load."""
        genset_model.reset()
        # Request only 10 kW when starting
        res = genset_model.step(
            target_online=True, power_setpoint_kw=10.0, ambient_temp_c=-10.0, dt_hours=1.0
        )
        assert res["power_kw"] == 45.0  # clamped to 30% of 150 kW

    def test_cold_start_delay_and_warmup_ramp(self, genset_model: GensetModel):
        """Cold-start warmup restricts max power for cold_start_delay_min (15 min)."""
        genset_model.reset()
        dt_min = 1.0 / 60.0  # 1-minute steps

        # Step 1: Start genset requesting full 150 kW
        # At t=1 min, warmup fraction is 1/15. Max power is 45 + (1/15)*(150-45) = 52 kW
        res1 = genset_model.step(
            target_online=True, power_setpoint_kw=150.0, ambient_temp_c=-10.0, dt_hours=dt_min
        )
        assert res1["is_warming_up"]
        assert res1["power_kw"] < 150.0

        # Run through minute 14: still warming up
        for _ in range(13):
            res_mid = genset_model.step(
                target_online=True, power_setpoint_kw=150.0, ambient_temp_c=-10.0, dt_hours=dt_min
            )
            assert res_mid["is_warming_up"]

        # Minute 15: warmup complete!
        res15 = genset_model.step(
            target_online=True, power_setpoint_kw=150.0, ambient_temp_c=-10.0, dt_hours=dt_min
        )
        assert not res15["is_warming_up"]
        assert res15["power_kw"] == 150.0

    def test_min_uptime_enforcement(self, genset_model: GensetModel):
        """Generator cannot be stopped before min_uptime_min (60 min)."""
        genset_model.reset()
        # Start and run for 30 minutes
        genset_model.step(
            target_online=True, power_setpoint_kw=50.0, ambient_temp_c=-10.0, dt_hours=0.5
        )
        assert genset_model.runtime_min == 30.0
        assert not genset_model.can_stop()

        # Attempt to shut down at t=30 min -> must stay online
        res = genset_model.step(
            target_online=False, power_setpoint_kw=0.0, ambient_temp_c=-10.0, dt_hours=0.25
        )
        assert res["is_online"]
        assert genset_model.is_online

        # Advance past 60 min (run 30 more minutes -> runtime = 75 min)
        genset_model.step(
            target_online=True, power_setpoint_kw=50.0, ambient_temp_c=-10.0, dt_hours=0.5
        )
        assert genset_model.can_stop()

        # Now shut down successfully
        res_stop = genset_model.step(
            target_online=False, power_setpoint_kw=0.0, ambient_temp_c=-10.0, dt_hours=0.25
        )
        assert not res_stop["is_online"]
        assert not genset_model.is_online

    def test_min_downtime_enforcement(self, genset_model: GensetModel):
        """Generator cannot restart before min_downtime_min (30 min)."""
        genset_model.reset()
        # Run for 60 min and stop
        genset_model.step(
            target_online=True, power_setpoint_kw=50.0, ambient_temp_c=-10.0, dt_hours=1.0
        )
        genset_model.step(
            target_online=False, power_setpoint_kw=0.0, ambient_temp_c=-10.0, dt_hours=0.1
        )
        assert not genset_model.is_online

        # Downtime is now 6 min (< 30 min). Attempt to restart -> must stay offline
        res = genset_model.step(
            target_online=True, power_setpoint_kw=50.0, ambient_temp_c=-10.0, dt_hours=0.1
        )
        assert not res["is_online"]

        # Advance downtime past 30 min (downtime = 6 + 6 + 20 = 32 min)
        genset_model.step(
            target_online=False, power_setpoint_kw=0.0, ambient_temp_c=-10.0, dt_hours=20.0 / 60.0
        )
        assert genset_model.can_start()

        # Restart now succeeds
        res_restart = genset_model.step(
            target_online=True, power_setpoint_kw=50.0, ambient_temp_c=-10.0, dt_hours=0.1
        )
        assert res_restart["is_online"]

    def test_waste_heat_recovery(self, genset_model: GensetModel):
        """Waste heat matches recovery_efficiency * (fuel_thermal - power)."""
        genset_model.reset()
        # Run at 100 kW for 1 hour
        res = genset_model.step(
            target_online=True, power_setpoint_kw=100.0, ambient_temp_c=-10.0, dt_hours=1.0
        )
        fuel_rate = res["fuel_rate_l_per_h"]
        power = res["power_kw"]
        fuel_thermal = fuel_rate * DIESEL_LHV_KWH_PER_L
        expected_heat = genset_model.config.heat_recovery_efficiency * (fuel_thermal - power)

        assert pytest.approx(res["waste_heat_kw"], rel=1e-3) == expected_heat
        assert res["waste_heat_kw"] > 0.0

    def test_fault_injection_and_recovery(self, genset_model: GensetModel):
        """Fault immediately trips genset and prevents restart until cleared."""
        genset_model.reset()
        genset_model.step(
            target_online=True, power_setpoint_kw=50.0, ambient_temp_c=-10.0, dt_hours=1.0
        )
        assert genset_model.is_online

        # Inject trip fault
        genset_model.inject_fault()
        assert not genset_model.is_online
        assert genset_model.is_faulted

        # Attempting to run returns 0 power
        res = genset_model.step(
            target_online=True, power_setpoint_kw=50.0, ambient_temp_c=-10.0, dt_hours=1.0
        )
        assert not res["is_online"]
        assert res["power_kw"] == 0.0

        # Clear fault
        genset_model.clear_fault()
        assert not genset_model.is_faulted
        # Must satisfy min downtime before starting
        genset_model.step(
            target_online=False, power_setpoint_kw=0.0, ambient_temp_c=-10.0, dt_hours=0.6
        )
        res_recovered = genset_model.step(
            target_online=True, power_setpoint_kw=50.0, ambient_temp_c=-10.0, dt_hours=0.5
        )
        assert res_recovered["is_online"]
