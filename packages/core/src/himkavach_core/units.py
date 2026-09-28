"""Physical units, conversion constants, and validation helpers for HimKavach.

All calculations across HimKavach standardise on SI and international engineering units:
- Power: Kilowatts (kW)
- Energy: Kilowatt-hours (kWh)
- Volume: Litres (L)
- Temperature: Degrees Celsius (°C)
- Speed: Metres per second (m/s)
- Pressure: Hectopascals (hPa)
- Irradiance: Watts per square metre (W/m²)
- Angle: Degrees (°)
- Time: Seconds (s) or Hours (h) with explicit conversion
"""

from typing import Final

# Energy & Power Conversions
KW_TO_W: Final[float] = 1000.0
W_TO_KW: Final[float] = 0.001
KWH_TO_JOULES: Final[float] = 3.6e6
JOULES_TO_KWH: Final[float] = 1.0 / 3.6e6
KWH_TO_MJ: Final[float] = 3.6
MJ_TO_KWH: Final[float] = 1.0 / 3.6

# Fuel Properties (Polar Grade Diesel / Jet A-1)
# Lower Heating Value (LHV) of Arctic diesel: ~42.8 MJ/kg, density ~0.84 kg/L -> ~36.0 MJ/L -> ~10.0 kWh/L
DIESEL_LHV_MJ_PER_L: Final[float] = 35.8
DIESEL_LHV_KWH_PER_L: Final[float] = DIESEL_LHV_MJ_PER_L / 3.6  # ~9.94 kWh/L
DIESEL_CO2_KG_PER_L: Final[float] = 2.68  # kg CO2 emitted per litre burned
DIESEL_DENSITY_KG_PER_L: Final[float] = 0.84

# Time Conversions
HOURS_PER_DAY: Final[float] = 24.0
MINUTES_PER_HOUR: Final[float] = 60.0
SECONDS_PER_MINUTE: Final[float] = 60.0
SECONDS_PER_HOUR: Final[float] = 3600.0

# Physical Constants
AIR_DENSITY_SEA_LEVEL_KG_M3: Final[float] = 1.225
SPECIFIC_HEAT_WATER_KJ_KG_K: Final[float] = 4.184
LATENT_HEAT_ICE_MELTING_KJ_KG: Final[float] = 334.0


def celsius_to_kelvin(temp_c: float) -> float:
    """Convert Celsius to Kelvin."""
    return temp_c + 273.15


def kelvin_to_celsius(temp_k: float) -> float:
    """Convert Kelvin to Celsius."""
    return temp_k - 273.15


def air_density(temp_c: float, pressure_hpa: float) -> float:
    """Compute dry air density given temperature in Celsius and pressure in hPa.

    rho = p / (R_specific * T)
    where R_specific = 287.058 J/(kg*K), p in Pa.
    """
    temp_k = celsius_to_kelvin(temp_c)
    pressure_pa = pressure_hpa * 100.0
    r_specific = 287.058
    return pressure_pa / (r_specific * temp_k)
