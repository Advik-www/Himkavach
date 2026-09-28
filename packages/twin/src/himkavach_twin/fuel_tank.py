"""Fuel tank inventory model with consumption tracking and leak injection.

Tracks bulk diesel inventory against generator burn, supports scheduled
resupply events, and allows injecting calibrated leak faults for testing.
"""

from __future__ import annotations

from himkavach_core.contracts.station import FuelConfig


class FuelTankModel:
    """Diesel fuel tank inventory tracker."""

    def __init__(self, config: FuelConfig) -> None:
        self.config = config
        self._volume_l: float = config.initial_inventory_l
        self._total_consumed_l: float = 0.0
        self._total_leaked_l: float = 0.0
        self._leak_rate_l_per_h: float = 0.0  # injected leak

    @property
    def volume_l(self) -> float:
        return self._volume_l

    @property
    def total_consumed_l(self) -> float:
        return self._total_consumed_l

    @property
    def total_leaked_l(self) -> float:
        return self._total_leaked_l

    @property
    def is_leaking(self) -> bool:
        return self._leak_rate_l_per_h > 0.0

    @property
    def fill_fraction(self) -> float:
        return self._volume_l / self.config.tank_capacity_l

    def step(self, fuel_burned_l: float, dt_hours: float = 1.0) -> dict[str, float]:
        """Update tank for one timestep.

        Parameters
        ----------
        fuel_burned_l : float
            Fuel consumed by generators this step (litres).
        dt_hours : float
            Timestep duration in hours.

        Returns dict with keys:
        - volume_l: current tank level
        - fuel_burned_l: actual fuel drawn for engines
        - fuel_leaked_l: fuel lost to leak this step
        - total_consumed_l: cumulative engine consumption
        - total_leaked_l: cumulative leak losses
        """
        # Compute leak volume
        leaked = self._leak_rate_l_per_h * dt_hours

        # Total drawdown
        total_draw = fuel_burned_l + leaked

        # Can't draw more than what's in the tank
        if total_draw > self._volume_l:
            # Proportionally reduce
            ratio = self._volume_l / total_draw if total_draw > 0 else 0.0
            fuel_burned_l *= ratio
            leaked *= ratio
            total_draw = fuel_burned_l + leaked

        self._volume_l = max(0.0, self._volume_l - total_draw)
        self._total_consumed_l += fuel_burned_l
        self._total_leaked_l += leaked

        return {
            "volume_l": self._volume_l,
            "fuel_burned_l": fuel_burned_l,
            "fuel_leaked_l": leaked,
            "total_consumed_l": self._total_consumed_l,
            "total_leaked_l": self._total_leaked_l,
        }

    def inject_leak(self, rate_l_per_h: float) -> None:
        """Start a fuel leak at the given rate."""
        self._leak_rate_l_per_h = max(0.0, rate_l_per_h)

    def stop_leak(self) -> None:
        """Stop any active leak."""
        self._leak_rate_l_per_h = 0.0

    def resupply(self, volume_l: float) -> float:
        """Add fuel (resupply delivery). Returns actual volume added."""
        headroom = self.config.tank_capacity_l - self._volume_l
        added = min(volume_l, headroom)
        self._volume_l += added
        return added

    def reset(self) -> None:
        """Reset to initial state."""
        self._volume_l = self.config.initial_inventory_l
        self._total_consumed_l = 0.0
        self._total_leaked_l = 0.0
        self._leak_rate_l_per_h = 0.0
