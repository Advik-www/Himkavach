"""Wind turbine plant model with power curve, cut-out hysteresis, icing derating,
and air-density correction.

Physics:
- Cubic power curve between cut-in and rated speed
- Air density correction (proportional to density ratio vs 1.225 kg/m³)
- High-wind cut-out at configured speed, with restart hysteresis:
  wind must remain below restart_speed for restart_dwell_min consecutive minutes
- Icing derating when conditions flagged
"""

from __future__ import annotations

from himkavach_core.contracts.station import WindTurbineConfig
from himkavach_core.units import air_density


class WindTurbineModel:
    """Physics-based wind turbine model with cut-out hysteresis and icing."""

    def __init__(self, config: WindTurbineConfig) -> None:
        self.config = config
        self._is_cut_out: bool = False
        self._minutes_below_restart: float = 0.0

    @property
    def is_cut_out(self) -> bool:
        return self._is_cut_out

    def _power_curve(self, wind_speed_m_s: float) -> float:
        """Compute normalized power output [0, 1] from wind speed.

        Uses cubic interpolation between cut-in and rated, flat at rated to cut-out.
        """
        v = wind_speed_m_s
        v_ci = self.config.cut_in_speed_m_s
        v_r = self.config.rated_speed_m_s
        v_co = self.config.cut_out_speed_m_s

        if v < v_ci:
            return 0.0
        elif v < v_r:
            # Cubic power region
            return ((v - v_ci) / (v_r - v_ci)) ** 3
        elif v <= v_co:
            return 1.0
        else:
            return 0.0  # above cut-out

    def _update_cutout_state(self, wind_speed_m_s: float, dt_minutes: float) -> None:
        """Update cut-out hysteresis state machine.

        - If wind exceeds cut-out speed: enter cut-out immediately
        - To restart: wind must stay below restart speed for restart_dwell_min
        """
        if not self._is_cut_out:
            if wind_speed_m_s > self.config.cut_out_speed_m_s:
                self._is_cut_out = True
                self._minutes_below_restart = 0.0
        else:
            if wind_speed_m_s <= self.config.restart_speed_m_s:
                self._minutes_below_restart += dt_minutes
                if self._minutes_below_restart >= self.config.restart_dwell_min:
                    self._is_cut_out = False
                    self._minutes_below_restart = 0.0
            else:
                self._minutes_below_restart = 0.0

    def step(
        self,
        wind_speed_m_s: float,
        temperature_c: float,
        pressure_hpa: float,
        is_icing: bool = False,
        dt_hours: float = 1.0,
    ) -> dict[str, float]:
        """Compute turbine output for one timestep.

        Parameters
        ----------
        wind_speed_m_s : float
            Hub-height wind speed in m/s.
        temperature_c : float
            Ambient temperature in °C.
        pressure_hpa : float
            Surface pressure in hPa.
        is_icing : bool
            Whether icing conditions are active.
        dt_hours : float
            Timestep duration in hours.

        Returns dict with keys:
        - power_kw: electrical output
        - is_cut_out: whether turbine is in cut-out lockout
        - air_density_kg_m3: computed air density
        - density_correction: density ratio correction factor
        - icing_derate: applied icing derating factor
        """
        dt_minutes = dt_hours * 60.0

        # Update cut-out hysteresis
        self._update_cutout_state(wind_speed_m_s, dt_minutes)

        if self._is_cut_out:
            return {
                "power_kw": 0.0,
                "is_cut_out": True,
                "air_density_kg_m3": air_density(temperature_c, pressure_hpa),
                "density_correction": 1.0,
                "icing_derate": 1.0,
            }

        # Power curve
        normalized_power = self._power_curve(wind_speed_m_s)

        # Air density correction
        rho = air_density(temperature_c, pressure_hpa)
        rho_ref = 1.225  # sea-level standard
        density_factor = rho / rho_ref  # cold dense air = more power

        # Icing derating
        icing_factor = self.config.icing_derate_factor if is_icing else 1.0

        # Output power
        power_kw = self.config.rated_power_kw * normalized_power * density_factor * icing_factor
        power_kw = max(0.0, power_kw)

        return {
            "power_kw": power_kw,
            "is_cut_out": False,
            "air_density_kg_m3": rho,
            "density_correction": density_factor,
            "icing_derate": icing_factor,
        }

    def reset(self) -> None:
        """Reset model state."""
        self._is_cut_out = False
        self._minutes_below_restart = 0.0
