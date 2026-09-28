"""Property-based tests for HimKavach core contracts using Hypothesis."""

from datetime import UTC, datetime

from himkavach_core.contracts import (
    BatteryConfig,
    GensetConfig,
    Scenario,
    ScenarioSet,
    ScenarioStep,
)
from hypothesis import given
from hypothesis import strategies as st


@given(
    rated_kw=st.floats(min_value=1.0, max_value=5000.0),
    min_ratio=st.floats(min_value=0.0, max_value=1.0),
    fuel_intercept=st.floats(min_value=0.0, max_value=1.0),
    fuel_slope=st.floats(min_value=0.0, max_value=1.0),
)
def test_genset_config_properties(
    rated_kw: float, min_ratio: float, fuel_intercept: float, fuel_slope: float
) -> None:
    g = GensetConfig(
        id="G_HYPOTHESIS",
        rated_power_kw=rated_kw,
        min_load_ratio=min_ratio,
        fuel_intercept_l_per_h_kw=fuel_intercept,
        fuel_slope_l_per_h_kw=fuel_slope,
    )
    assert g.min_stable_power_kw >= 0.0
    assert g.min_stable_power_kw <= g.rated_power_kw + 1e-6


@given(
    cap_kwh=st.floats(min_value=10.0, max_value=10000.0),
    eff_ch=st.floats(min_value=0.5, max_value=1.0),
    eff_dis=st.floats(min_value=0.5, max_value=1.0),
)
def test_battery_efficiency_property(cap_kwh: float, eff_ch: float, eff_dis: float) -> None:
    b = BatteryConfig(
        id="B_HYPOTHESIS",
        capacity_kwh=cap_kwh,
        max_charge_kw=cap_kwh,
        max_discharge_kw=cap_kwh,
        charge_efficiency=eff_ch,
        discharge_efficiency=eff_dis,
    )
    rte = b.round_trip_efficiency
    assert 0.25 <= rte <= 1.0


@given(
    p1=st.floats(min_value=0.05, max_value=0.95),
)
def test_scenario_set_probabilities_sum(p1: float) -> None:
    p2 = 1.0 - p1
    now = datetime(2026, 6, 21, tzinfo=UTC)
    step = ScenarioStep(
        step_index=0,
        timestamp=now,
        duration_hours=1.0,
        wind_avail_kw=10.0,
        solar_avail_kw=0.0,
        ambient_temp_c=-20.0,
        load_tier0_kw=40.0,
        load_tier1_kw=20.0,
        load_tier2_kw=50.0,
        load_tier3_kw=10.0,
    )
    s1 = Scenario(scenario_id="s1", probability=p1, steps=[step])
    s2 = Scenario(scenario_id="s2", probability=p2, steps=[step])

    sset = ScenarioSet(set_id="SET_HYP", created_at=now, scenarios=[s1, s2])
    assert sset.count == 2
