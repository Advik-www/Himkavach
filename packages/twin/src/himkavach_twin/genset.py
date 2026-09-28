"""Diesel generator set model with nonlinear fuel curve, cold-start delay,
minimum stable load, minimum up/down time constraints, waste heat recovery,
and stochastic failure potential.

Physics:
- Fuel consumption: F = a * u * P_rated + b * P_output (L/h)
  where u is on/off status, a is the no-load intercept, b is the marginal slope
- Cold-start delay: generator must warm up for cold_start_delay_min before accepting
  loads above min stable load. During warmup, output ramps linearly.
- Min up/down time: once started, must run for min_uptime_min; once stopped, must rest
  for min_downtime_min
- Waste heat: recoverable fraction of fuel thermal energy for space heating
- Engine temperature tracking for cold-start effects
"""

from __future__ import annotations

from himkavach_core.contracts.station import GensetConfig
from himkavach_core.units import DIESEL_LHV_KWH_PER_L


class GensetModel:
    """Physics-based diesel generator model for polar conditions."""

    def __init__(self, config: GensetConfig) -> None:
        self.config = config
        self._is_online: bool = False
        self._power_kw: float = 0.0
        self._fuel_rate_l_per_h: float = 0.0
        self._runtime_min: float = 0.0  # current run
        self._downtime_min: float = 60.0  # start rested (>min_downtime)
        self._warmup_elapsed_min: float = 0.0
        self._cumulative_run_hours: float = 0.0
        self._total_fuel_consumed_l: float = 0.0
        self._engine_temp_c: float = -10.0  # start cold
        self._is_faulted: bool = False
        self._total_starts: int = 0

    @property
    def is_online(self) -> bool:
        return self._is_online

    @property
    def power_kw(self) -> float:
        return self._power_kw

    @property
    def fuel_rate_l_per_h(self) -> float:
        return self._fuel_rate_l_per_h

    @property
    def runtime_min(self) -> float:
        return self._runtime_min

    @property
    def downtime_min(self) -> float:
        return self._downtime_min

    @property
    def cumulative_run_hours(self) -> float:
        return self._cumulative_run_hours

    @property
    def total_fuel_consumed_l(self) -> float:
        return self._total_fuel_consumed_l

    @property
    def engine_temp_c(self) -> float:
        return self._engine_temp_c

    @property
    def is_faulted(self) -> bool:
        return self._is_faulted

    @property
    def total_starts(self) -> int:
        return self._total_starts

    def _compute_fuel_rate(self, power_kw: float) -> float:
        """Compute fuel consumption rate (L/h) using linear fuel curve.

        F = a * P_rated + b * P_output
        where a = fuel_intercept_l_per_h_kw (no-load burn per kW rated)
              b = fuel_slope_l_per_h_kw (marginal per kW output)
        """
        if not self._is_online:
            return 0.0
        no_load = self.config.fuel_intercept_l_per_h_kw * self.config.rated_power_kw
        marginal = self.config.fuel_slope_l_per_h_kw * power_kw
        return no_load + marginal

    def _compute_waste_heat_kw(self, fuel_rate_l_per_h: float, power_kw: float) -> float:
        """Compute recoverable waste heat in kW_thermal.

        Total fuel thermal power = fuel_rate * LHV
        Waste heat = recovery_efficiency * (fuel_thermal - electrical_output)
        """
        fuel_thermal_kw = fuel_rate_l_per_h * DIESEL_LHV_KWH_PER_L  # kW thermal
        waste_heat_available = max(0.0, fuel_thermal_kw - power_kw)
        return self.config.heat_recovery_efficiency * waste_heat_available

    def _update_engine_temp(self, ambient_temp_c: float, dt_hours: float) -> None:
        """Simple engine thermal model.

        Running engine tends toward ~85°C operating temp.
        Stopped engine cools toward ambient.
        """
        if self._is_online:
            target = 85.0
            tau = 0.5  # fast warmup when running (hours)
        else:
            target = ambient_temp_c
            tau = 2.0  # slower cooldown
        self._engine_temp_c += (target - self._engine_temp_c) * dt_hours / tau

    def _is_warmup_complete(self) -> bool:
        """Check if cold-start warmup has elapsed."""
        return self._warmup_elapsed_min >= self.config.cold_start_delay_min

    def can_start(self) -> bool:
        """Check if generator can be started (min downtime satisfied, not faulted)."""
        return (
            not self._is_online
            and not self._is_faulted
            and self._downtime_min >= self.config.min_downtime_min
        )

    def can_stop(self) -> bool:
        """Check if generator can be stopped (min uptime satisfied)."""
        return self._is_online and self._runtime_min >= self.config.min_uptime_min

    def step(
        self,
        target_online: bool,
        power_setpoint_kw: float,
        ambient_temp_c: float,
        dt_hours: float = 1.0,
    ) -> dict[str, float]:
        """Simulate one timestep of generator operation.

        Parameters
        ----------
        target_online : bool
            Desired on/off state.
        power_setpoint_kw : float
            Desired electrical output in kW.
        ambient_temp_c : float
            Ambient temperature in °C.
        dt_hours : float
            Timestep duration in hours.

        Returns dict with keys:
        - power_kw: actual electrical output
        - fuel_rate_l_per_h: fuel consumption rate
        - fuel_consumed_l: fuel consumed this step
        - waste_heat_kw: recoverable waste heat
        - is_online: current status
        - is_warming_up: whether in cold-start warmup
        - engine_temp_c: engine temperature
        - just_started: whether a start event occurred
        - just_stopped: whether a stop event occurred
        """
        dt_min = dt_hours * 60.0
        just_started = False
        just_stopped = False

        # Handle faulted state
        if self._is_faulted:
            self._is_online = False
            self._power_kw = 0.0
            self._fuel_rate_l_per_h = 0.0
            self._downtime_min += dt_min
            self._update_engine_temp(ambient_temp_c, dt_hours)
            return {
                "power_kw": 0.0,
                "fuel_rate_l_per_h": 0.0,
                "fuel_consumed_l": 0.0,
                "waste_heat_kw": 0.0,
                "is_online": False,
                "is_warming_up": False,
                "engine_temp_c": self._engine_temp_c,
                "just_started": False,
                "just_stopped": False,
            }

        # State transitions
        if target_online and not self._is_online:
            if self.can_start():
                self._is_online = True
                self._runtime_min = 0.0
                self._warmup_elapsed_min = 0.0
                self._total_starts += 1
                just_started = True
        elif not target_online and self._is_online:
            if self.can_stop():
                self._is_online = False
                self._downtime_min = 0.0
                self._power_kw = 0.0
                self._fuel_rate_l_per_h = 0.0
                just_stopped = True

        if self._is_online:
            self._runtime_min += dt_min
            self._warmup_elapsed_min += dt_min
            self._cumulative_run_hours += dt_hours

            # Determine max available power during warmup
            if self._is_warmup_complete():
                max_power = self.config.rated_power_kw
            else:
                # Linear ramp from min stable to rated during warmup
                warmup_frac = self._warmup_elapsed_min / self.config.cold_start_delay_min
                max_power = self.config.min_stable_power_kw + warmup_frac * (
                    self.config.rated_power_kw - self.config.min_stable_power_kw
                )

            # Clamp to [min_stable, max_power]
            actual_power = max(self.config.min_stable_power_kw, min(power_setpoint_kw, max_power))

            # Apply ramp rate limit
            max_ramp = self.config.ramp_rate_kw_per_min * dt_min
            if actual_power > self._power_kw + max_ramp:
                actual_power = self._power_kw + max_ramp
            elif actual_power < self._power_kw - max_ramp:
                actual_power = max(self.config.min_stable_power_kw, self._power_kw - max_ramp)

            self._power_kw = actual_power
            self._fuel_rate_l_per_h = self._compute_fuel_rate(actual_power)
            fuel_consumed = self._fuel_rate_l_per_h * dt_hours
            self._total_fuel_consumed_l += fuel_consumed
            waste_heat = self._compute_waste_heat_kw(self._fuel_rate_l_per_h, actual_power)

        else:
            self._downtime_min += dt_min
            self._power_kw = 0.0
            self._fuel_rate_l_per_h = 0.0
            fuel_consumed = 0.0
            waste_heat = 0.0

        self._update_engine_temp(ambient_temp_c, dt_hours)

        return {
            "power_kw": self._power_kw,
            "fuel_rate_l_per_h": self._fuel_rate_l_per_h,
            "fuel_consumed_l": fuel_consumed,
            "waste_heat_kw": waste_heat,
            "is_online": self._is_online,
            "is_warming_up": self._is_online and not self._is_warmup_complete(),
            "engine_temp_c": self._engine_temp_c,
            "just_started": just_started,
            "just_stopped": just_stopped,
        }

    def inject_fault(self) -> None:
        """Force an immediate generator trip/failure."""
        self._is_faulted = True
        self._is_online = False
        self._power_kw = 0.0
        self._fuel_rate_l_per_h = 0.0

    def clear_fault(self) -> None:
        """Clear fault flag (repair complete). Generator still needs to be restarted."""
        self._is_faulted = False
        self._downtime_min = 0.0  # reset downtime to enforce min_downtime before restart

    def reset(self, ambient_temp_c: float = -10.0) -> None:
        """Reset all state."""
        self._is_online = False
        self._power_kw = 0.0
        self._fuel_rate_l_per_h = 0.0
        self._runtime_min = 0.0
        self._downtime_min = 60.0
        self._warmup_elapsed_min = 0.0
        self._cumulative_run_hours = 0.0
        self._total_fuel_consumed_l = 0.0
        self._engine_temp_c = ambient_temp_c
        self._is_faulted = False
        self._total_starts = 0
