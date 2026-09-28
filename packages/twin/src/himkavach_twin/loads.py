"""Tiered electrical loads and building thermal model for the polar station.

Contains:
1. LoadModel: tier-aware electrical load generator with diurnal and seasonal patterns
2. ThermalModel: lumped RC building thermal dynamics with wind chill, waste heat,
   and auxiliary electric heating
3. SnowMeltTankModel: potable water storage from snow melting (deferrable load)

Physics (Thermal):
- Single-node RC model: C * dT/dt = (T_amb - T_in)/R + Q_heat + Q_internal
  where R = 1/heat_loss_coeff, C = heat_capacity
- Wind chill increases effective heat loss (adds a wind-dependent conductance term)
- Waste heat from generators offsets electric heating
- Indoor temperature clamped between comfort bounds

Physics (Loads):
- Each tier has base + variable component with diurnal and seasonal patterns
- Tier 0 (life support): nearly constant, slight cold-weather increase
- Tier 1 (science): flat with small random perturbation
- Tier 2 (comfort): strong diurnal pattern (meals, activity)
- Tier 3 (deferrable): scheduled bursts (snow melting, vehicle charging)
"""

from __future__ import annotations

import math

from himkavach_core.contracts.station import LoadTierConfig, ThermalConfig
from numpy.random import Generator


class ThermalModel:
    """Lumped RC building thermal model for polar research station."""

    def __init__(self, config: ThermalConfig, initial_indoor_temp_c: float = 20.0) -> None:
        self.config = config
        self._indoor_temp_c: float = initial_indoor_temp_c

    @property
    def indoor_temp_c(self) -> float:
        return self._indoor_temp_c

    def _wind_chill_conductance(self, wind_speed_m_s: float) -> float:
        """Additional thermal conductance from wind, kW/°C.

        Wind increases infiltration and convective heat loss.
        Approximate as 0.05 * sqrt(wind_speed) kW/°C additional loss.
        """
        return 0.05 * math.sqrt(max(0.0, wind_speed_m_s))

    def step(
        self,
        ambient_temp_c: float,
        wind_speed_m_s: float,
        waste_heat_kw: float,
        aux_heating_kw: float,
        internal_gains_kw: float,
        dt_hours: float = 1.0,
    ) -> dict[str, float]:
        """Simulate one timestep of building thermal dynamics.

        Parameters
        ----------
        ambient_temp_c : float
            Outdoor ambient temperature.
        wind_speed_m_s : float
            Wind speed for wind chill effect.
        waste_heat_kw : float
            Recoverable waste heat from generators (kW_th).
        aux_heating_kw : float
            Electric auxiliary heating (kW_e, assumed COP=1).
        internal_gains_kw : float
            Internal heat from occupancy, lighting, equipment (kW_th).
        dt_hours : float
            Timestep in hours.

        Returns dict with keys:
        - indoor_temp_c: indoor temperature after step
        - heat_loss_kw: total heat loss to environment
        - total_heating_kw: total heating delivered
        - heating_demand_kw: heating needed to maintain setpoint
        """
        # Total thermal conductance
        base_ua = self.config.building_heat_loss_kw_per_c  # kW/°C
        wind_ua = self._wind_chill_conductance(wind_speed_m_s)
        total_ua = base_ua + wind_ua

        # Heat loss
        heat_loss = total_ua * (self._indoor_temp_c - ambient_temp_c)

        # Total heating input
        total_heating = waste_heat_kw + aux_heating_kw + internal_gains_kw

        # RC dynamics: C * dT = (Q_in - Q_loss) * dt
        c_th = self.config.building_heat_capacity_kwh_per_c  # kWh/°C
        dt_temp = (total_heating - heat_loss) * dt_hours / c_th
        self._indoor_temp_c += dt_temp

        # Compute steady-state heating demand to maintain setpoint
        heating_demand = (
            total_ua * (self.config.setpoint_temp_c - ambient_temp_c) - internal_gains_kw
        )
        heating_demand = max(0.0, heating_demand)

        return {
            "indoor_temp_c": self._indoor_temp_c,
            "heat_loss_kw": heat_loss,
            "total_heating_kw": total_heating,
            "heating_demand_kw": heating_demand,
        }

    def reset(self, indoor_temp_c: float = 20.0) -> None:
        self._indoor_temp_c = indoor_temp_c


class SnowMeltTankModel:
    """Potable water storage from snow melting (deferrable load)."""

    def __init__(
        self,
        capacity_l: float,
        melter_power_kw: float,
        initial_level_l: float | None = None,
    ) -> None:
        self.capacity_l = capacity_l
        self.melter_power_kw = melter_power_kw
        # Energy to melt 1L of snow and heat to potable temp:
        # ~0.1 kWh/L (334 kJ/kg latent + ~80 kJ sensible to ~20°C, total ~414 kJ ≈ 0.115 kWh)
        self.energy_per_litre_kwh: float = 0.115
        self._level_l: float = initial_level_l if initial_level_l is not None else capacity_l * 0.7
        self._total_melted_l: float = 0.0

    @property
    def level_l(self) -> float:
        return self._level_l

    @property
    def fill_fraction(self) -> float:
        return self._level_l / self.capacity_l

    def step(
        self,
        melter_active: bool,
        consumption_l_per_h: float,
        dt_hours: float = 1.0,
    ) -> dict[str, float]:
        """Step the water tank model.

        Parameters
        ----------
        melter_active : bool
            Whether the snow melter is running (drawing melter_power_kw).
        consumption_l_per_h : float
            Water consumption rate (L/h).
        dt_hours : float
            Timestep in hours.

        Returns:
        - level_l: current tank level
        - power_consumed_kw: electrical power consumed by melter
        - water_produced_l: water added by melting
        - water_consumed_l: water drawn from tank
        """
        # Consumption
        consumed = consumption_l_per_h * dt_hours
        consumed = min(consumed, self._level_l)
        self._level_l -= consumed

        # Production from melting
        power = 0.0
        produced = 0.0
        if melter_active and self._level_l < self.capacity_l:
            power = self.melter_power_kw
            produced = power * dt_hours / self.energy_per_litre_kwh
            headroom = self.capacity_l - self._level_l
            produced = min(produced, headroom)
            self._level_l += produced
            self._total_melted_l += produced

        return {
            "level_l": self._level_l,
            "power_consumed_kw": power,
            "water_produced_l": produced,
            "water_consumed_l": consumed,
        }

    def reset(self, level_l: float | None = None) -> None:
        self._level_l = level_l if level_l is not None else self.capacity_l * 0.7
        self._total_melted_l = 0.0


class LoadModel:
    """Tiered electrical load generator with diurnal and seasonal patterns."""

    def __init__(
        self,
        tier_configs: list[LoadTierConfig],
        rng: Generator,
    ) -> None:
        self.tier_configs = {tc.tier: tc for tc in tier_configs}
        self.rng = rng

    def generate_loads(
        self,
        hour_of_day: int,
        day_of_year: int,
        ambient_temp_c: float,
        wind_speed_m_s: float,
    ) -> dict[int, float]:
        """Generate load demand for each tier at a given moment.

        Parameters
        ----------
        hour_of_day : int
            Hour 0-23.
        day_of_year : int
            Day 1-365.
        ambient_temp_c : float
            Outdoor temperature (drives heating-related base loads).
        wind_speed_m_s : float
            Wind speed (adds wind chill driven heating load).

        Returns dict mapping tier number to demanded power in kW.
        """
        loads: dict[int, float] = {}

        for tier_num, cfg in self.tier_configs.items():
            base = cfg.base_kw
            variable_range = cfg.peak_kw - cfg.base_kw

            if tier_num == 0:
                # Life support: nearly constant, slight increase in extreme cold
                cold_factor = max(0.0, (-30.0 - ambient_temp_c) * 0.002)  # per °C below -30
                noise = self.rng.normal(0, 0.5)
                load = base + cold_factor * variable_range + noise

            elif tier_num == 1:
                # Science: flat with small random fluctuation
                noise = self.rng.normal(0, 1.0)
                load = base + noise

            elif tier_num == 2:
                # Comfort/operations: strong diurnal (meals at 7,12,18; workshop 9-17)
                # Seasonal: higher in winter (more indoor activity)
                seasonal_phase = 2.0 * math.pi * (day_of_year - 172) / 365.0
                winter_factor = 0.5 * (1.0 - math.cos(seasonal_phase))  # 0=summer, 1=winter
                meal_factor = 0.0
                if hour_of_day in (7, 8):
                    meal_factor = 0.4
                elif hour_of_day in (12, 13):
                    meal_factor = 0.5
                elif hour_of_day in (18, 19):
                    meal_factor = 0.6
                elif 9 <= hour_of_day <= 17:
                    meal_factor = 0.2  # workshop/lab activity
                elif 20 <= hour_of_day <= 22:
                    meal_factor = 0.15  # evening recreation
                else:
                    meal_factor = 0.0

                diurnal = meal_factor + 0.1 * winter_factor
                noise = self.rng.normal(0, 2.0)
                load = base + diurnal * variable_range + noise

            elif tier_num == 3:
                # Deferrable: random bursts of snow melting, vehicle charging
                # More likely during day hours when operators are active
                burst_prob = 0.15 if 8 <= hour_of_day <= 20 else 0.03
                if self.rng.random() < burst_prob:
                    burst = self.rng.uniform(0.3, 0.8) * variable_range
                else:
                    burst = 0.0
                noise = self.rng.normal(0, 1.0)
                load = base * 0.3 + burst + noise  # lower baseline between bursts
            else:
                load = base

            loads[tier_num] = max(0.0, min(cfg.peak_kw, load))

        return loads

    def reset(self, rng: Generator | None = None) -> None:
        if rng is not None:
            self.rng = rng
