"""Solar PV plant model with snow-cover state and cold-temperature efficiency gain.

Physics:
- pvlib for solar position and clear-sky irradiance at the configured tilt/azimuth
- Cloud modifier from ambient GHI vs clear-sky ratio
- Snow accumulation (from snowfall) and shedding (from temperature and irradiance)
- Cold-temperature efficiency boost (negative temp coefficient = power gain in cold)
- Polar day/night handled via pvlib solar position
"""

from __future__ import annotations

import math

import pvlib
from himkavach_core.contracts.station import SolarPVConfig
from himkavach_core.contracts.weather import WeatherObs


class SolarPVModel:
    """Physics-based PV array model with snow-cover dynamics."""

    def __init__(self, config: SolarPVConfig, latitude: float, longitude: float) -> None:
        self.config = config
        self.latitude = latitude
        self.longitude = longitude
        self.location = pvlib.location.Location(latitude, longitude, tz="UTC")

        # Snow cover state: fraction of array covered [0, 1]
        self._snow_cover: float = 0.0

    @property
    def snow_cover(self) -> float:
        return self._snow_cover

    @snow_cover.setter
    def snow_cover(self, value: float) -> None:
        self._snow_cover = max(0.0, min(1.0, value))

    def _get_poa_irradiance(self, weather: WeatherObs) -> float:
        """Compute plane-of-array irradiance using pvlib solar position."""
        times = weather.timestamp
        sol_pos = self.location.get_solarposition(times)
        solar_zenith = float(sol_pos["apparent_zenith"].iloc[0])
        solar_azimuth = float(sol_pos["azimuth"].iloc[0])

        if solar_zenith >= 90.0:
            return 0.0

        # Use isotropic sky model for POA from GHI/DNI/DHI
        ghi = weather.ghi_w_m2
        dni = weather.dni_w_m2
        dhi = weather.dhi_w_m2

        if ghi <= 0.0:
            return 0.0

        # Angle of incidence
        aoi = float(
            pvlib.irradiance.aoi(
                self.config.tilt_deg,
                self.config.azimuth_deg,
                solar_zenith,
                solar_azimuth,
            )
        )

        # Beam component on tilted surface
        cos_aoi = math.cos(math.radians(aoi))
        if cos_aoi < 0:
            cos_aoi = 0.0
        cos_zenith = math.cos(math.radians(solar_zenith))
        if cos_zenith < 0.01:
            cos_zenith = 0.01

        beam_poa = dni * cos_aoi

        # Isotropic sky diffuse
        diffuse_poa = dhi * (1.0 + math.cos(math.radians(self.config.tilt_deg))) / 2.0

        # Ground reflected (assume albedo ~0.7 for snow, high at poles)
        ground_poa = ghi * 0.7 * (1.0 - math.cos(math.radians(self.config.tilt_deg))) / 2.0

        return max(0.0, beam_poa + diffuse_poa + ground_poa)

    def _update_snow_cover(self, weather: WeatherObs, dt_hours: float) -> None:
        """Update snow accumulation and shedding state."""
        # Accumulation: snowfall adds to cover (1 mm/h LWE for 1 hour covers ~5%)
        accumulation = 0.0
        if weather.snowfall_rate_mm_h > 0.0:
            accumulation = weather.snowfall_rate_mm_h * dt_hours * 0.05

        # Shedding: temperature above threshold, irradiance, and gravity
        shedding = 0.0
        if weather.temperature_c > self.config.snow_shed_temp_c:
            temp_excess = weather.temperature_c - self.config.snow_shed_temp_c
            shedding += 0.02 * temp_excess * dt_hours

        if weather.ghi_w_m2 > 50.0:
            shedding += 0.005 * (weather.ghi_w_m2 / 500.0) * dt_hours

        if self.config.tilt_deg > 45.0 and self._snow_cover > 0.0:
            shedding += 0.003 * (self.config.tilt_deg / 90.0) * dt_hours

        self._snow_cover = max(0.0, min(1.0, self._snow_cover + accumulation - shedding))

    def step(
        self,
        weather: WeatherObs,
        dt_hours: float = 1.0,
    ) -> dict[str, float]:
        """Compute PV output for one timestep.

        Returns dict with keys:
        - power_kw: net electrical output
        - poa_irradiance_w_m2: plane-of-array irradiance
        - snow_cover_ratio: current snow cover fraction
        - temp_derate_factor: temperature efficiency multiplier (>1 in cold)
        """
        # Update snow dynamics
        self._update_snow_cover(weather, dt_hours)

        # Get POA irradiance
        poa = self._get_poa_irradiance(weather)

        # Temperature derating (negative coefficient = power GAIN in cold)
        # Reference temperature is 25°C (STC)
        cell_temp = weather.temperature_c + 20.0  # simple NOCT approximation offset
        temp_factor = 1.0 + self.config.temp_coeff_per_c * (cell_temp - 25.0)
        temp_factor = max(0.5, min(1.5, temp_factor))  # clamp to reasonable range

        # Snow cover reduces output
        snow_factor = 1.0 - self._snow_cover

        # Effective power
        # At STC (1000 W/m²), output = peak_power_kw
        poa_ratio = poa / 1000.0 if poa > 0 else 0.0
        power_kw = self.config.peak_power_kw * poa_ratio * temp_factor * snow_factor
        power_kw = max(0.0, power_kw)

        return {
            "power_kw": power_kw,
            "poa_irradiance_w_m2": poa,
            "snow_cover_ratio": self._snow_cover,
            "temp_derate_factor": temp_factor,
        }

    def reset(self, snow_cover: float = 0.0) -> None:
        """Reset model state."""
        self._snow_cover = max(0.0, min(1.0, snow_cover))
