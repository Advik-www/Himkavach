"""Synthetic fallback weather generator for offline operation.

Generates physically plausible hourly polar weather using:
- Ornstein-Uhlenbeck (mean-reverting) processes for temperature, wind, pressure
- Diurnal and seasonal sinusoidal modulation
- Polar day/night transitions based on latitude and day-of-year
- Correlated humidity and irradiance tied to temperature and cloud state
- Simple cloud-state Markov chain driving snowfall and irradiance attenuation

All randomness uses an explicit numpy.random.Generator for reproducibility.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
from himkavach_core.contracts.weather import WeatherObs
from numpy.random import Generator


def _solar_declination_rad(day_of_year: int) -> float:
    """Solar declination angle in radians (Spencer formula)."""
    b = 2.0 * math.pi * (day_of_year - 1) / 365.0
    return (
        0.006918
        - 0.399912 * math.cos(b)
        + 0.070257 * math.sin(b)
        - 0.006758 * math.cos(2 * b)
        + 0.000907 * math.sin(2 * b)
        - 0.002697 * math.cos(3 * b)
        + 0.00148 * math.sin(3 * b)
    )


def _max_solar_elevation(latitude_deg: float, day_of_year: int) -> float:
    """Maximum solar elevation angle at solar noon (degrees)."""
    lat_rad = math.radians(latitude_deg)
    decl = _solar_declination_rad(day_of_year)
    sin_elev = math.sin(lat_rad) * math.sin(decl) + math.cos(lat_rad) * math.cos(decl)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_elev))))


def _ou_step(
    x: float,
    mu: float,
    theta: float,
    sigma: float,
    dt: float,
    rng: Generator,
) -> float:
    """Single Ornstein-Uhlenbeck step: dx = theta*(mu - x)*dt + sigma*dW."""
    dw = rng.normal(0.0, math.sqrt(dt))
    return x + theta * (mu - x) * dt + sigma * dw


def generate_synthetic_weather(
    latitude: float,
    longitude: float,
    start: datetime,
    hours: int,
    rng: Generator,
    *,
    winter_mean_temp_c: float = -25.0,
    summer_mean_temp_c: float = -2.0,
    mean_wind_m_s: float = 8.0,
    wind_variability: float = 4.0,
    mean_pressure_hpa: float = 985.0,
) -> list[WeatherObs]:
    """Generate hourly synthetic polar weather observations.

    Parameters
    ----------
    latitude : float
        Station latitude (negative for Southern Hemisphere).
    longitude : float
        Station longitude.
    start : datetime
        Start timestamp (must be timezone-aware UTC).
    hours : int
        Number of hourly observations to generate.
    rng : Generator
        Seeded numpy random generator for reproducibility.
    winter_mean_temp_c : float
        Climatological mean temperature during polar winter.
    summer_mean_temp_c : float
        Climatological mean temperature during polar summer.
    mean_wind_m_s : float
        Long-term mean wind speed.
    wind_variability : float
        Standard deviation of OU wind noise.
    mean_pressure_hpa : float
        Long-term mean surface pressure.

    Returns
    -------
    list[WeatherObs]
        Hourly weather observations.
    """
    dt = 1.0  # 1-hour time step

    # OU process parameters
    theta_temp = 0.05  # slow mean-reversion for temperature
    sigma_temp = 1.5
    theta_wind = 0.15  # moderate mean-reversion for wind
    sigma_wind = wind_variability
    theta_press = 0.03  # slow pressure evolution
    sigma_press = 1.2

    # Initialize state
    day_of_year = start.timetuple().tm_yday
    seasonal_phase = 2.0 * math.pi * (day_of_year - 172) / 365.0  # peak summer ~Jun 21
    # For southern hemisphere, shift by 6 months
    if latitude < 0:
        seasonal_phase += math.pi

    seasonal_frac = 0.5 * (1.0 + math.cos(seasonal_phase))  # 1=summer, 0=winter
    mean_temp = winter_mean_temp_c + seasonal_frac * (summer_mean_temp_c - winter_mean_temp_c)

    temp = mean_temp + rng.normal(0, 3.0)
    wind = max(0.5, mean_wind_m_s + rng.normal(0, 2.0))
    pressure = mean_pressure_hpa + rng.normal(0, 3.0)

    # Cloud state: 0=clear, 1=partly cloudy, 2=overcast
    cloud_state = rng.choice([0, 1, 2], p=[0.3, 0.4, 0.3])
    cloud_transition = np.array(
        [
            [0.85, 0.12, 0.03],  # clear -> ...
            [0.10, 0.75, 0.15],  # partly -> ...
            [0.05, 0.20, 0.75],  # overcast -> ...
        ]
    )

    observations: list[WeatherObs] = []

    for h in range(hours):
        ts = start + timedelta(hours=h)
        current_doy = ts.timetuple().tm_yday
        hour_of_day = ts.hour

        # Seasonal modulation
        sp = 2.0 * math.pi * (current_doy - 172) / 365.0
        if latitude < 0:
            sp += math.pi
        sf = 0.5 * (1.0 + math.cos(sp))
        target_temp = winter_mean_temp_c + sf * (summer_mean_temp_c - winter_mean_temp_c)

        # Diurnal temperature cycle (small at poles, larger in summer)
        diurnal_amp = 2.0 * sf + 0.5  # 0.5-2.5°C amplitude
        diurnal = diurnal_amp * math.cos(2.0 * math.pi * (hour_of_day - 14) / 24.0)
        target_temp += diurnal

        # Step OU processes
        temp = _ou_step(temp, target_temp, theta_temp, sigma_temp, dt, rng)
        wind_target = mean_wind_m_s * (1.0 + 0.15 * math.cos(sp + math.pi))  # windier in winter
        wind = max(0.0, _ou_step(wind, wind_target, theta_wind, sigma_wind, dt, rng))
        pressure = _ou_step(pressure, mean_pressure_hpa, theta_press, sigma_press, dt, rng)

        # Cloud state transition
        cloud_state = rng.choice([0, 1, 2], p=cloud_transition[cloud_state])

        # Wind gust (proportional to mean wind)
        gust_factor = 1.0 + rng.exponential(0.15)
        gust = wind * gust_factor

        # Wind direction (slowly varying random walk)
        if h == 0:
            wind_dir = rng.uniform(0, 360)
        else:
            wind_dir = (wind_dir + rng.normal(0, 10)) % 360.0

        # Humidity: inversely correlated with temperature, higher when cloudy
        base_rh = 65.0 - 0.3 * temp  # colder = more RH (relative)
        cloud_rh_boost = [0.0, 5.0, 15.0][cloud_state]
        rh = max(20.0, min(100.0, base_rh + cloud_rh_boost + rng.normal(0, 5.0)))

        # Solar irradiance
        # Hour angle for approximate elevation
        hour_angle = 15.0 * (hour_of_day - 12.0)
        lat_rad = math.radians(latitude)
        decl = _solar_declination_rad(current_doy)
        sin_elev = math.sin(lat_rad) * math.sin(decl) + math.cos(lat_rad) * math.cos(
            decl
        ) * math.cos(math.radians(hour_angle))
        solar_elev = math.degrees(math.asin(max(-1.0, min(1.0, sin_elev))))

        if solar_elev > 0:
            # Simple clear-sky GHI approximation
            airmass = 1.0 / max(math.sin(math.radians(solar_elev)), 0.05)
            clear_sky_ghi = max(
                0.0, 1361.0 * math.sin(math.radians(solar_elev)) * (0.7 ** (airmass**0.678))
            )
            cloud_attenuation = [1.0, 0.55, 0.15][cloud_state]
            ghi = clear_sky_ghi * cloud_attenuation
            # DNI and DHI approximate split
            if cloud_state == 0:
                dni = ghi * 0.85
                dhi = ghi * 0.15
            elif cloud_state == 1:
                dni = ghi * 0.45
                dhi = ghi * 0.55
            else:
                dni = ghi * 0.10
                dhi = ghi * 0.90
        else:
            ghi = 0.0
            dni = 0.0
            dhi = 0.0

        # Snowfall: more likely when cloudy and cold, driven by cloud state
        snowfall_rate = 0.0
        if cloud_state == 2 and temp < -5.0:
            if rng.random() < 0.4:
                snowfall_rate = rng.exponential(1.5)  # mm/h LWE
        elif cloud_state == 1 and temp < -10.0:
            if rng.random() < 0.1:
                snowfall_rate = rng.exponential(0.5)

        # Pressure tendency (3h lookback approximation)
        press_tend_3h = 0.0
        if h >= 3:
            prev_obs = observations[h - 3]
            press_tend_3h = pressure - prev_obs.surface_pressure_hpa

        temp_tend_3h = 0.0
        if h >= 3:
            prev_obs = observations[h - 3]
            temp_tend_3h = temp - prev_obs.temperature_c

        # Icing risk: temp near 0, high humidity, wind present
        is_icing = -5.0 < temp < 2.0 and rh > 85.0 and wind > 5.0

        obs = WeatherObs(
            timestamp=ts,
            temperature_c=round(temp, 2),
            wind_speed_m_s=round(max(0.0, wind), 2),
            wind_direction_deg=round(wind_dir, 1),
            wind_gust_m_s=round(max(0.0, gust), 2),
            surface_pressure_hpa=round(pressure, 2),
            relative_humidity_pct=round(rh, 1),
            ghi_w_m2=round(max(0.0, ghi), 2),
            dni_w_m2=round(max(0.0, dni), 2),
            dhi_w_m2=round(max(0.0, dhi), 2),
            snowfall_rate_mm_h=round(max(0.0, snowfall_rate), 2),
            pressure_tendency_3h_hpa=round(press_tend_3h, 2),
            temp_tendency_3h_c=round(temp_tend_3h, 2),
            is_icing_risk=is_icing,
            storm_regime="CALM_NORMAL",
        )
        observations.append(obs)

    return observations
