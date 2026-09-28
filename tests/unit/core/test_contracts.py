"""Unit tests for HimKavach domain contracts."""

from datetime import UTC, datetime

import pytest
from himkavach_core.contracts import (
    BatteryConfig,
    BatteryState,
    CounterfactualEstimate,
    DecisionCard,
    DecisionFactor,
    FuelConfig,
    FuelState,
    GensetConfig,
    GensetState,
    LoadTierConfig,
    LoadTierState,
    OperatingLevel,
    RenewableState,
    Scenario,
    ScenarioSet,
    ScenarioStep,
    SolarPVConfig,
    StationConfig,
    StationState,
    ThermalConfig,
    ThermalState,
    WindTurbineConfig,
)
from pydantic import ValidationError


def test_genset_config_validation_and_properties() -> None:
    g = GensetConfig(
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
    assert g.min_stable_power_kw == pytest.approx(45.0)

    # Immutability check
    with pytest.raises(ValidationError):
        # frozen=True forbids attribute assignment
        g.rated_power_kw = 200.0  # type: ignore[misc]

    # Negative rated power should fail
    with pytest.raises(ValidationError):
        GensetConfig(id="GEN_BAD", rated_power_kw=-50.0)


def test_battery_config_validation() -> None:
    b = BatteryConfig(
        id="BESS_1",
        capacity_kwh=600.0,
        max_charge_kw=300.0,
        max_discharge_kw=300.0,
        charge_efficiency=0.96,
        discharge_efficiency=0.96,
        min_soc=0.10,
        max_soc=1.00,
    )
    assert b.round_trip_efficiency == pytest.approx(0.9216)

    # SoC > 1.0 must fail
    with pytest.raises(ValidationError):
        BatteryConfig(
            id="BESS_BAD",
            capacity_kwh=600.0,
            max_charge_kw=300.0,
            max_discharge_kw=300.0,
            min_soc=0.10,
            max_soc=1.20,
        )


def test_station_config_aggregate_capacities() -> None:
    station = StationConfig(
        station_id="STATION_TEST",
        name="Test Polar Station",
        latitude=-70.8,
        longitude=11.7,
        elevation_m=100.0,
        gensets=[
            GensetConfig(id="G1", rated_power_kw=150.0),
            GensetConfig(id="G2", rated_power_kw=150.0),
        ],
        battery=BatteryConfig(capacity_kwh=600.0, max_charge_kw=300.0, max_discharge_kw=300.0),
        wind_turbines=[
            WindTurbineConfig(id="W1", rated_power_kw=100.0),
            WindTurbineConfig(id="W2", rated_power_kw=100.0),
        ],
        pv_arrays=[SolarPVConfig(id="PV1", peak_power_kw=80.0)],
        thermal=ThermalConfig(),
        load_tiers=[
            LoadTierConfig(
                tier=0, name="Life Support", base_kw=40.0, peak_kw=45.0, voll_usd_per_kwh=10000.0
            ),
            LoadTierConfig(
                tier=1, name="Science", base_kw=20.0, peak_kw=25.0, voll_usd_per_kwh=500.0
            ),
            LoadTierConfig(
                tier=2, name="Comfort", base_kw=50.0, peak_kw=100.0, voll_usd_per_kwh=20.0
            ),
            LoadTierConfig(
                tier=3, name="Deferrable", base_kw=20.0, peak_kw=80.0, voll_usd_per_kwh=3.0
            ),
        ],
        fuel=FuelConfig(),
    )
    assert station.total_genset_capacity_kw == 300.0
    assert station.total_wind_capacity_kw == 200.0
    assert station.total_pv_capacity_kw == 80.0
    assert station.get_tier(0).name == "Life Support"

    with pytest.raises(KeyError):
        station.get_tier(9)


def test_station_state_properties() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
    state = StationState(
        station_id="STATION_TEST",
        timestamp=now,
        gensets=[
            GensetState(
                id="G1",
                is_online=True,
                electric_power_kw=100.0,
                fuel_rate_l_per_h=37.0,
                engine_temp_c=85.0,
                runtime_current_run_min=120,
                downtime_current_rest_min=0,
                cumulative_run_hours=1500.0,
            )
        ],
        battery=BatteryState(
            soc=0.75,
            stored_energy_kwh=450.0,
            cell_temp_c=18.0,
            power_kw=20.0,  # discharging 20 kW
        ),
        thermal=ThermalState(
            indoor_temp_c=20.5,
            water_tank_level_l=8000.0,
            total_heat_demand_kw=35.0,
        ),
        fuel=FuelState(
            tank_volume_l=120000.0,
            burn_rate_l_per_h=37.0,
            days_of_autonomy_at_current_burn=135.0,
            glide_path_target_l=115000.0,
            glide_path_delta_l=5000.0,
        ),
        loads=[
            LoadTierState(tier=0, demanded_kw=40.0, served_kw=40.0, shed_kw=0.0),
            LoadTierState(tier=1, demanded_kw=20.0, served_kw=20.0, shed_kw=0.0),
            LoadTierState(tier=2, demanded_kw=50.0, served_kw=50.0, shed_kw=0.0),
            LoadTierState(tier=3, demanded_kw=10.0, served_kw=10.0, shed_kw=0.0),
        ],
        renewables=RenewableState(
            wind_generated_kw=0.0,
            pv_generated_kw=0.0,
        ),
        survival_hours=72.0,
    )

    assert state.total_generation_kw == 100.0
    assert state.total_demanded_kw == 120.0
    assert state.total_served_kw == 120.0
    assert state.total_shed_kw == 0.0


def test_scenario_set_probability_validation() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
    step = ScenarioStep(
        step_index=0,
        timestamp=now,
        duration_hours=0.25,
        wind_avail_kw=50.0,
        solar_avail_kw=0.0,
        ambient_temp_c=-25.0,
        load_tier0_kw=40.0,
        load_tier1_kw=20.0,
        load_tier2_kw=50.0,
        load_tier3_kw=10.0,
    )

    s1 = Scenario(scenario_id="s1", probability=0.6, steps=[step])
    s2 = Scenario(scenario_id="s2", probability=0.4, steps=[step])
    scenario_set = ScenarioSet(set_id="SET_VALID", created_at=now, scenarios=[s1, s2])
    assert scenario_set.count == 2

    # If probabilities do not sum to 1.0, it must fail validation
    s_invalid = Scenario(scenario_id="s_bad", probability=0.2, steps=[step])
    with pytest.raises(ValidationError):
        ScenarioSet(set_id="SET_BAD", created_at=now, scenarios=[s1, s_invalid])


def test_decision_card_structure() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
    card = DecisionCard(
        card_id="CARD_001",
        timestamp=now,
        level=OperatingLevel.PRE_STORM,
        level_name="PRE_STORM",
        headline="Pre-Storm Thermal Pre-Heat & Dynamic Reserve Inflation",
        detailed_rationale="Blizzard onset probability exceeds 85% within next 12 hours.",
        trigger_factors=[
            DecisionFactor(
                factor_name="p_storm_12h",
                observed_value=0.88,
                threshold_value=0.70,
                unit="probability",
                description="High probability of severe katabatic storm onset",
            )
        ],
        storm_probability_next_12h=0.88,
        recommended_actions=[
            "Pre-heat building thermal mass to 23°C",
            "Accelerate snow melting batch to fill potable tank to 100%",
            "Inflate battery dynamic reserve floor to 65% SoC",
        ],
        counterfactual=CounterfactualEstimate(
            baseline_policy="B2_TUNED_RULES",
            fuel_delta_litres=42.5,
            risk_delta_cvar_pct=34.0,
            narrative="HimKavach avoids emergency generator cold-start during peak blizzard winds.",
        ),
        confidence_score=0.96,
    )
    assert card.level == OperatingLevel.PRE_STORM
    assert card.counterfactual.fuel_delta_litres > 0
