"""Unit tests for the Fuel Tank inventory model."""

import pytest
from himkavach_core.contracts.station import FuelConfig
from himkavach_twin.fuel_tank import FuelTankModel


@pytest.fixture
def fuel_config() -> FuelConfig:
    return FuelConfig(
        tank_capacity_l=180000.0,
        initial_inventory_l=150000.0,
        days_to_resupply=300,
        contingency_days=45,
        fuel_unit_cost_usd_per_l=2.50,
    )


@pytest.fixture
def fuel_tank(fuel_config: FuelConfig) -> FuelTankModel:
    return FuelTankModel(config=fuel_config)


class TestFuelTankModel:
    def test_burn_drawdown(self, fuel_tank: FuelTankModel):
        """Fuel consumption by engines reduces inventory proportionally."""
        initial = fuel_tank.volume_l
        res = fuel_tank.step(fuel_burned_l=100.0, dt_hours=1.0)
        assert res["volume_l"] == initial - 100.0
        assert res["fuel_burned_l"] == 100.0
        assert res["fuel_leaked_l"] == 0.0
        assert fuel_tank.total_consumed_l == 100.0

    def test_leak_injection(self, fuel_tank: FuelTankModel):
        """Injected leak results in fuel loss even without engine burn."""
        initial = fuel_tank.volume_l
        fuel_tank.inject_leak(rate_l_per_h=5.0)
        assert fuel_tank.is_leaking

        # 4 hours of leak with 0 burn = 20 L lost
        res = fuel_tank.step(fuel_burned_l=0.0, dt_hours=4.0)
        assert res["fuel_leaked_l"] == 20.0
        assert res["volume_l"] == initial - 20.0
        assert fuel_tank.total_leaked_l == 20.0

        # Stop leak
        fuel_tank.stop_leak()
        assert not fuel_tank.is_leaking
        res_stopped = fuel_tank.step(fuel_burned_l=0.0, dt_hours=1.0)
        assert res_stopped["fuel_leaked_l"] == 0.0

    def test_tank_empty_limiting(self, fuel_tank: FuelTankModel):
        """Cannot draw more fuel than currently stored in tank."""
        fuel_tank.reset()
        fuel_tank._volume_l = 50.0  # artificially set near empty

        # Request 100 L burn
        res = fuel_tank.step(fuel_burned_l=100.0, dt_hours=1.0)
        assert res["volume_l"] == 0.0
        assert res["fuel_burned_l"] == 50.0  # limited to available volume

    def test_resupply(self, fuel_tank: FuelTankModel):
        """Resupply adds fuel up to capacity ceiling."""
        fuel_tank.reset()  # 150,000 L of 180,000 L capacity -> 30,000 L headroom
        added = fuel_tank.resupply(20000.0)
        assert added == 20000.0
        assert fuel_tank.volume_l == 170000.0

        # Try to overfill by 25,000 L when only 10,000 L headroom remains
        added_overfill = fuel_tank.resupply(25000.0)
        assert added_overfill == 10000.0
        assert fuel_tank.volume_l == 180000.0
        assert fuel_tank.fill_fraction == 1.0

    def test_reset(self, fuel_tank: FuelTankModel):
        """Reset restores initial volume and clears counters."""
        fuel_tank.step(fuel_burned_l=1000.0, dt_hours=1.0)
        fuel_tank.inject_leak(10.0)
        fuel_tank.reset()
        assert fuel_tank.volume_l == fuel_tank.config.initial_inventory_l
        assert fuel_tank.total_consumed_l == 0.0
        assert fuel_tank.total_leaked_l == 0.0
        assert not fuel_tank.is_leaking
