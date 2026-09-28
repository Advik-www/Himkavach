"""Battery energy storage system model with equivalent-circuit dynamics,
temperature-dependent derating, cold-charge protection, heater load,
and cycle degradation tracking.

Physics:
- Simple equivalent-circuit: OCV(SoC) + R(T)*I model for voltage and losses
- Temperature-dependent internal resistance: increases ~1.5x per 20°C below 25°C
- Cold-charge lockout: zero charge power when cell_temp < min_temp_c_for_charging
- Charge/discharge power derating based on temperature
- Enclosure heater activates when cell_temp < heater_activation_temp
- Degradation: throughput-based calendar + cycling wear using equivalent full cycles
"""

from __future__ import annotations

import math

from himkavach_core.contracts.station import BatteryConfig


class BatteryModel:
    """Physics-based Li-ion battery model for polar conditions."""

    # Temperature at which heater activates (above cold-charge limit to give margin)
    HEATER_ACTIVATION_TEMP_C: float = 5.0

    def __init__(self, config: BatteryConfig, initial_soc: float = 0.75) -> None:
        self.config = config
        self._soc: float = max(config.min_soc, min(config.max_soc, initial_soc))
        self._cell_temp_c: float = 20.0  # start warm, cools toward ambient
        self._total_throughput_kwh: float = 0.0
        self._equivalent_full_cycles: float = 0.0
        self._soh: float = 1.0  # state of health [0, 1]
        self._heater_active: bool = False

    @property
    def soc(self) -> float:
        return self._soc

    @property
    def cell_temp_c(self) -> float:
        return self._cell_temp_c

    @property
    def stored_energy_kwh(self) -> float:
        return self._soc * self.config.capacity_kwh * self._soh

    @property
    def total_throughput_kwh(self) -> float:
        return self._total_throughput_kwh

    @property
    def equivalent_full_cycles(self) -> float:
        return self._equivalent_full_cycles

    @property
    def soh(self) -> float:
        return self._soh

    @property
    def heater_active(self) -> bool:
        return self._heater_active

    def _resistance_factor(self, temp_c: float) -> float:
        """Temperature-dependent internal resistance multiplier.

        Resistance increases exponentially in cold. At 25°C factor=1.0,
        at 0°C ~1.8x, at -20°C ~3.5x, at -40°C ~7x.
        """
        return math.exp(0.03 * (25.0 - temp_c))

    def _charge_derate(self, temp_c: float) -> float:
        """Temperature-based charge power derating factor [0, 1].

        Below min_temp_c_for_charging: zero charge allowed.
        Between min_temp and 10°C: linear ramp from 0.0 to 0.5.
        Between 10°C and 25°C: linear ramp from 0.5 to 1.0.
        Above 25°C: 1.0.
        """
        if temp_c < self.config.min_temp_c_for_charging:
            return 0.0
        elif temp_c < 10.0:
            span = 10.0 - self.config.min_temp_c_for_charging
            if span <= 0:
                return 0.5
            return 0.5 * (temp_c - self.config.min_temp_c_for_charging) / span
        elif temp_c < 25.0:
            return 0.5 + 0.5 * (temp_c - 10.0) / 15.0
        else:
            return 1.0

    def _discharge_derate(self, temp_c: float) -> float:
        """Temperature-based discharge power derating factor [0, 1].

        Discharge is less restricted than charge but still derated in extreme cold.
        Below -30°C: 0.3. Between -30°C and 0°C: linear ramp from 0.3 to 0.8.
        Between 0°C and 25°C: ramp from 0.8 to 1.0. Above 25°C: 1.0.
        """
        if temp_c < -30.0:
            return 0.3
        elif temp_c < 0.0:
            return 0.3 + 0.5 * (temp_c + 30.0) / 30.0
        elif temp_c < 25.0:
            return 0.8 + 0.2 * temp_c / 25.0
        else:
            return 1.0

    def _update_cell_temperature(
        self, ambient_temp_c: float, power_kw: float, dt_hours: float
    ) -> None:
        """Update cell temperature via simple thermal model.

        Cell temperature tends toward ambient with a thermal time constant,
        plus internal heat generation from I²R losses, plus heater contribution.
        """
        # Thermal time constant (~2-4 hours for enclosure)
        tau_hours = 3.0

        # Internal heat generation (proportional to power and resistance factor)
        r_factor = self._resistance_factor(self._cell_temp_c)
        # Approximate: losses as fraction of power, scaled by R factor
        # At high R factor (cold), more heat generated from same power
        internal_heat_c_per_hour = abs(power_kw) * r_factor * 0.003  # heuristic

        # Heater contribution
        heater_heat = 0.0
        if self._heater_active:
            heater_heat = self.config.heater_power_kw * 0.15  # °C/hour from heater kW

        # First-order thermal dynamics
        self._cell_temp_c += (
            (ambient_temp_c - self._cell_temp_c) / tau_hours
            + internal_heat_c_per_hour
            + heater_heat
        ) * dt_hours

    def step(
        self,
        power_setpoint_kw: float,
        ambient_temp_c: float,
        dt_hours: float = 1.0,
    ) -> dict[str, float]:
        """Simulate one timestep of battery operation.

        Parameters
        ----------
        power_setpoint_kw : float
            Requested power: >0 for discharge, <0 for charge.
        ambient_temp_c : float
            External ambient temperature in °C.
        dt_hours : float
            Timestep duration in hours.

        Returns dict with keys:
        - actual_power_kw: actual terminal power (>0 discharge, <0 charge)
        - soc: state of charge after step
        - cell_temp_c: cell temperature after step
        - heater_power_kw: heater consumption this step
        - losses_kw: internal losses this step
        - charge_derate: applied charge derate factor
        - discharge_derate: applied discharge derate factor
        - stored_energy_kwh: usable stored energy
        """
        effective_capacity = self.config.capacity_kwh * self._soh

        # Heater logic
        self._heater_active = self._cell_temp_c < self.HEATER_ACTIVATION_TEMP_C
        heater_kw = self.config.heater_power_kw if self._heater_active else 0.0

        # Determine available charge/discharge power
        ch_derate = self._charge_derate(self._cell_temp_c)
        dis_derate = self._discharge_derate(self._cell_temp_c)

        max_charge_kw = self.config.max_charge_kw * ch_derate
        max_discharge_kw = self.config.max_discharge_kw * dis_derate

        # Apply SoC limits
        # Max charge limited by remaining capacity
        soc_headroom = (self.config.max_soc - self._soc) * effective_capacity / dt_hours
        max_charge_kw = min(max_charge_kw, max(0.0, soc_headroom / self.config.charge_efficiency))

        # Max discharge limited by available energy above min SoC
        soc_available = (self._soc - self.config.min_soc) * effective_capacity / dt_hours
        max_discharge_kw = min(
            max_discharge_kw, max(0.0, soc_available * self.config.discharge_efficiency)
        )

        # Clip setpoint to feasible range
        if power_setpoint_kw > 0:
            # Discharge
            actual_power = min(power_setpoint_kw, max_discharge_kw)
            energy_from_battery = actual_power * dt_hours / self.config.discharge_efficiency
            self._soc -= energy_from_battery / effective_capacity
            losses = energy_from_battery - actual_power * dt_hours
        elif power_setpoint_kw < 0:
            # Charge
            charge_kw = min(abs(power_setpoint_kw), max_charge_kw)
            actual_power = -charge_kw
            energy_to_battery = charge_kw * dt_hours * self.config.charge_efficiency
            self._soc += energy_to_battery / effective_capacity
            losses = charge_kw * dt_hours - energy_to_battery
        else:
            actual_power = 0.0
            losses = 0.0

        # Clamp SoC
        self._soc = max(self.config.min_soc, min(self.config.max_soc, self._soc))

        # Update throughput and degradation
        energy_throughput = abs(actual_power) * dt_hours
        self._total_throughput_kwh += energy_throughput
        self._equivalent_full_cycles = self._total_throughput_kwh / (2.0 * self.config.capacity_kwh)

        # Simple degradation: 0.02% capacity loss per equivalent full cycle
        # Plus calendar fade: 0.001% per hour
        cycle_fade = 0.0002 * energy_throughput / (2.0 * self.config.capacity_kwh)
        calendar_fade = 0.00001 * dt_hours
        self._soh = max(0.5, self._soh - cycle_fade - calendar_fade)

        # Update temperature
        self._update_cell_temperature(ambient_temp_c, actual_power, dt_hours)

        return {
            "actual_power_kw": actual_power,
            "soc": self._soc,
            "cell_temp_c": self._cell_temp_c,
            "heater_power_kw": heater_kw,
            "losses_kw": losses / dt_hours if dt_hours > 0 else 0.0,
            "charge_derate": ch_derate,
            "discharge_derate": dis_derate,
            "stored_energy_kwh": self._soc * effective_capacity,
        }

    def reset(self, soc: float = 0.75, cell_temp_c: float = 20.0) -> None:
        """Reset model state."""
        self._soc = max(self.config.min_soc, min(self.config.max_soc, soc))
        self._cell_temp_c = cell_temp_c
        self._total_throughput_kwh = 0.0
        self._equivalent_full_cycles = 0.0
        self._soh = 1.0
        self._heater_active = False
