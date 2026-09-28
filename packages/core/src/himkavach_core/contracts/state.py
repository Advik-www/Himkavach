"""Station state and telemetry contracts."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class GensetState(BaseModel):
    """Real-time operational state of a diesel generator."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    is_online: bool
    electric_power_kw: Annotated[float, Field(ge=0.0)]
    fuel_rate_l_per_h: Annotated[float, Field(ge=0.0)]
    engine_temp_c: float
    runtime_current_run_min: Annotated[int, Field(ge=0)]
    downtime_current_rest_min: Annotated[int, Field(ge=0)]
    cumulative_run_hours: Annotated[float, Field(ge=0.0)]
    heat_recovered_kw: Annotated[float, Field(ge=0.0, default=0.0)]
    is_faulted: bool = False


class BatteryState(BaseModel):
    """Real-time state of the battery energy storage system."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    soc: Annotated[float, Field(ge=0.0, le=1.0, description="State of Charge (0.0 to 1.0)")]
    stored_energy_kwh: Annotated[float, Field(ge=0.0, description="Available usable energy")]
    cell_temp_c: float = Field(description="Mean internal cell temperature in °C")
    power_kw: float = Field(description="Net terminal power in kW (>0 discharging, <0 charging)")
    voltage_v: Annotated[float, Field(gt=0.0, default=400.0)]
    current_a: float = Field(default=0.0)
    heater_active: bool = False
    soh: Annotated[float, Field(ge=0.0, le=1.0, default=1.0, description="State of Health")]
    charge_derate_factor: Annotated[float, Field(ge=0.0, le=1.0, default=1.0)]


class ThermalState(BaseModel):
    """Real-time state of thermal building and water storage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    indoor_temp_c: float
    water_tank_level_l: Annotated[float, Field(ge=0.0)]
    aux_heater_power_kw: Annotated[float, Field(ge=0.0, default=0.0)]
    snow_melter_power_kw: Annotated[float, Field(ge=0.0, default=0.0)]
    total_heat_demand_kw: Annotated[float, Field(ge=0.0)]


class FuelState(BaseModel):
    """Real-time diesel inventory state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tank_volume_l: Annotated[float, Field(ge=0.0)]
    burn_rate_l_per_h: Annotated[float, Field(ge=0.0)]
    days_of_autonomy_at_current_burn: Annotated[float, Field(ge=0.0)]
    glide_path_target_l: Annotated[float, Field(ge=0.0)]
    glide_path_delta_l: float = Field(
        description="Surplus (>0) or deficit (<0) relative to glide path"
    )


class LoadTierState(BaseModel):
    """Real-time load and unserved demand for a tier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tier: int
    demanded_kw: Annotated[float, Field(ge=0.0)]
    served_kw: Annotated[float, Field(ge=0.0)]
    shed_kw: Annotated[float, Field(ge=0.0)]
    interrupted_duration_min: Annotated[int, Field(ge=0, default=0)]


class RenewableState(BaseModel):
    """Real-time renewable generation summary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    wind_generated_kw: Annotated[float, Field(ge=0.0)]
    wind_curtailed_kw: Annotated[float, Field(ge=0.0, default=0.0)]
    turbines_cut_out_count: Annotated[int, Field(ge=0, default=0)]
    pv_generated_kw: Annotated[float, Field(ge=0.0)]
    pv_curtailed_kw: Annotated[float, Field(ge=0.0, default=0.0)]
    pv_snow_cover_ratio: Annotated[float, Field(ge=0.0, le=1.0, default=0.0)]


class StationState(BaseModel):
    """Full snapshot of station telemetry at a specific minute timestamp."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    station_id: str
    timestamp: datetime
    gensets: list[GensetState]
    battery: BatteryState
    thermal: ThermalState
    fuel: FuelState
    loads: list[LoadTierState]
    renewables: RenewableState
    survival_hours: Annotated[
        float,
        Field(ge=0.0, description="Hours Tier 0+1 can be served with N-1 genset & 0 renewables"),
    ]

    @property
    def total_generation_kw(self) -> float:
        """Total active electrical generation."""
        gen_kw = sum(g.electric_power_kw for g in self.gensets)
        wind_kw = self.renewables.wind_generated_kw
        pv_kw = self.renewables.pv_generated_kw
        return gen_kw + wind_kw + pv_kw

    @property
    def total_demanded_kw(self) -> float:
        """Total demanded electrical power across all tiers."""
        return sum(load.demanded_kw for load in self.loads)

    @property
    def total_served_kw(self) -> float:
        """Total served electrical power across all tiers."""
        return sum(load.served_kw for load in self.loads)

    @property
    def total_shed_kw(self) -> float:
        """Total unserved / shed power."""
        return sum(load.shed_kw for load in self.loads)
