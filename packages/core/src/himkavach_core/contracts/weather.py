"""Weather observation and time series contracts."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class WeatherObs(BaseModel):
    """Single-timestamp meteorological observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime
    temperature_c: float = Field(description="Dry bulb 2m ambient air temperature (°C)")
    wind_speed_m_s: Annotated[float, Field(ge=0.0, description="10m mean wind speed (m/s)")]
    wind_direction_deg: Annotated[
        float, Field(ge=0.0, le=360.0, default=0.0, description="Wind direction (degrees)")
    ]
    wind_gust_m_s: Annotated[
        float, Field(ge=0.0, default=0.0, description="Peak 3-second gust speed (m/s)")
    ]
    surface_pressure_hpa: Annotated[
        float, Field(gt=0.0, default=985.0, description="Atmospheric barometric pressure (hPa)")
    ]
    relative_humidity_pct: Annotated[
        float, Field(ge=0.0, le=100.0, default=70.0, description="Relative humidity (%)")
    ]
    ghi_w_m2: Annotated[
        float, Field(ge=0.0, default=0.0, description="Global Horizontal Irradiance (W/m²)")
    ]
    dni_w_m2: Annotated[
        float, Field(ge=0.0, default=0.0, description="Direct Normal Irradiance (W/m²)")
    ]
    dhi_w_m2: Annotated[
        float, Field(ge=0.0, default=0.0, description="Diffuse Horizontal Irradiance (W/m²)")
    ]
    snowfall_rate_mm_h: Annotated[
        float,
        Field(ge=0.0, default=0.0, description="Liquid water equivalent snowfall rate (mm/h)"),
    ]
    pressure_tendency_3h_hpa: float = Field(
        default=0.0, description="3-hour pressure barometric change (hPa/3h)"
    )
    temp_tendency_3h_c: float = Field(
        default=0.0, description="3-hour ambient temperature change (°C/3h)"
    )
    is_icing_risk: bool = Field(default=False, description="Active rotor icing conditions flag")
    storm_regime: str = Field(
        default="CALM_NORMAL",
        description="Weather regime: CALM_NORMAL, BLIZZARD, KATABATIC, POLAR_NIGHT",
    )


class WeatherTimeSeries(BaseModel):
    """Time-indexed sequence of weather observations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    station_id: str
    observations: list[WeatherObs] = Field(..., min_length=1)

    @property
    def start_time(self) -> datetime:
        return self.observations[0].timestamp

    @property
    def end_time(self) -> datetime:
        return self.observations[-1].timestamp

    @property
    def count(self) -> int:
        return len(self.observations)
