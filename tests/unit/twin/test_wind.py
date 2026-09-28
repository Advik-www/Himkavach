"""Unit tests for the Wind Turbine plant model."""

import pytest
from himkavach_core.contracts.station import WindTurbineConfig
from himkavach_twin.wind import WindTurbineModel


@pytest.fixture
def wind_config() -> WindTurbineConfig:
    return WindTurbineConfig(
        id="TURBINE_TEST",
        rated_power_kw=100.0,
        cut_in_speed_m_s=3.0,
        rated_speed_m_s=12.0,
        cut_out_speed_m_s=25.0,
        restart_speed_m_s=20.0,
        restart_dwell_min=10,
        hub_height_m=25.0,
        icing_derate_factor=0.85,
    )


@pytest.fixture
def wind_model(wind_config: WindTurbineConfig) -> WindTurbineModel:
    return WindTurbineModel(config=wind_config)


class TestWindTurbineModel:
    def test_below_cut_in_produces_zero(self, wind_model: WindTurbineModel):
        """Wind speed below cut-in generates zero power."""
        res = wind_model.step(wind_speed_m_s=2.0, temperature_c=0.0, pressure_hpa=1013.25)
        assert res["power_kw"] == 0.0
        assert not res["is_cut_out"]

    def test_cubic_power_curve(self, wind_model: WindTurbineModel):
        """Power curve is cubic between cut-in and rated speed."""
        # Standard sea-level density: rho = 1.225 kg/m3 => density factor ~ 1.0 at ~15°C and 1013.25 hPa
        # At midpoint (v - v_ci)/(v_r - v_ci) = (7.5 - 3)/(12 - 3) = 4.5/9 = 0.5
        # (0.5)^3 = 0.125
        res = wind_model.step(wind_speed_m_s=7.5, temperature_c=15.0, pressure_hpa=1013.25)
        expected_power = 100.0 * 0.125 * res["density_correction"]
        assert pytest.approx(res["power_kw"], rel=1e-3) == expected_power

    def test_rated_speed_produces_rated_power(self, wind_model: WindTurbineModel):
        """Between rated speed and cut-out speed, normalized power is 1.0."""
        res_rated = wind_model.step(wind_speed_m_s=12.0, temperature_c=15.0, pressure_hpa=1013.25)
        assert (
            pytest.approx(res_rated["power_kw"], rel=1e-3)
            == 100.0 * res_rated["density_correction"]
        )

        res_high = wind_model.step(wind_speed_m_s=20.0, temperature_c=15.0, pressure_hpa=1013.25)
        assert (
            pytest.approx(res_high["power_kw"], rel=1e-3) == 100.0 * res_high["density_correction"]
        )

    def test_cut_out_above_threshold(self, wind_model: WindTurbineModel):
        """Wind speed exceeding cut-out trips turbine to cut-out lockout."""
        res = wind_model.step(wind_speed_m_s=26.0, temperature_c=0.0, pressure_hpa=1000.0)
        assert res["power_kw"] == 0.0
        assert res["is_cut_out"]
        assert wind_model.is_cut_out

    def test_cut_out_restart_hysteresis_and_dwell(self, wind_model: WindTurbineModel):
        """Turbine enters cut-out at >25 m/s and stays locked out until <20 m/s for 10 min."""
        # 1. Trigger cut-out (dt = 1 minute = 1/60 hr)
        dt_1min = 1.0 / 60.0
        res = wind_model.step(
            wind_speed_m_s=28.0, temperature_c=-10.0, pressure_hpa=985.0, dt_hours=dt_1min
        )
        assert res["is_cut_out"]
        assert res["power_kw"] == 0.0

        # 2. Wind drops to 22 m/s (below cut-out 25, but ABOVE restart 20) -> must stay locked out
        for _ in range(15):
            res = wind_model.step(
                wind_speed_m_s=22.0, temperature_c=-10.0, pressure_hpa=985.0, dt_hours=dt_1min
            )
            assert res["is_cut_out"]
            assert res["power_kw"] == 0.0

        # 3. Wind drops to 15 m/s (below restart 20). Need 10 minutes dwell.
        # Minutes 1 to 9: still cut out
        for _ in range(9):
            res = wind_model.step(
                wind_speed_m_s=15.0, temperature_c=-10.0, pressure_hpa=985.0, dt_hours=dt_1min
            )
            assert res["is_cut_out"]
            assert res["power_kw"] == 0.0

        # Minute 10: dwell complete, turbine restarts and produces power!
        res = wind_model.step(
            wind_speed_m_s=15.0, temperature_c=-10.0, pressure_hpa=985.0, dt_hours=dt_1min
        )
        assert not res["is_cut_out"]
        assert res["power_kw"] > 0.0

    def test_cut_out_dwell_interrupted_by_gust(self, wind_model: WindTurbineModel):
        """If wind spikes back above restart threshold during dwell, dwell timer resets."""
        dt_1min = 1.0 / 60.0
        # Trigger cut-out
        wind_model.step(
            wind_speed_m_s=30.0, temperature_c=-10.0, pressure_hpa=985.0, dt_hours=dt_1min
        )
        assert wind_model.is_cut_out

        # Dwell for 5 minutes at 15 m/s
        for _ in range(5):
            wind_model.step(
                wind_speed_m_s=15.0, temperature_c=-10.0, pressure_hpa=985.0, dt_hours=dt_1min
            )
        assert wind_model.is_cut_out

        # Gust spikes to 23 m/s (> restart_speed 20 m/s) -> resets dwell counter
        wind_model.step(
            wind_speed_m_s=23.0, temperature_c=-10.0, pressure_hpa=985.0, dt_hours=dt_1min
        )
        assert wind_model.is_cut_out

        # Another 5 minutes at 15 m/s is not enough because the counter was reset (needs full 10 min)
        for _ in range(5):
            res = wind_model.step(
                wind_speed_m_s=15.0, temperature_c=-10.0, pressure_hpa=985.0, dt_hours=dt_1min
            )
        assert res["is_cut_out"]

    def test_air_density_correction(self, wind_model: WindTurbineModel):
        """Cold air is denser, producing proportionally more aerodynamic power."""
        # Cold Antarctic air (-40°C, 985 hPa) vs warm air (+20°C, 985 hPa)
        res_cold = wind_model.step(wind_speed_m_s=10.0, temperature_c=-40.0, pressure_hpa=985.0)
        res_warm = wind_model.step(wind_speed_m_s=10.0, temperature_c=20.0, pressure_hpa=985.0)

        assert res_cold["air_density_kg_m3"] > res_warm["air_density_kg_m3"]
        assert res_cold["power_kw"] > res_warm["power_kw"]

    def test_icing_derating(self, wind_model: WindTurbineModel):
        """Icing derates power by the configured icing_derate_factor."""
        res_normal = wind_model.step(
            wind_speed_m_s=10.0, temperature_c=-5.0, pressure_hpa=985.0, is_icing=False
        )
        res_icing = wind_model.step(
            wind_speed_m_s=10.0, temperature_c=-5.0, pressure_hpa=985.0, is_icing=True
        )

        assert (
            pytest.approx(res_icing["power_kw"])
            == res_normal["power_kw"] * wind_model.config.icing_derate_factor
        )
        assert res_icing["icing_derate"] == wind_model.config.icing_derate_factor

    def test_reset(self, wind_model: WindTurbineModel):
        """Reset clears cut-out state and dwell timers."""
        wind_model.step(wind_speed_m_s=30.0, temperature_c=-10.0, pressure_hpa=985.0)
        assert wind_model.is_cut_out
        wind_model.reset()
        assert not wind_model.is_cut_out
