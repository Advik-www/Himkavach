"""Plant control action contracts."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class GensetDispatchCommand(BaseModel):
    """Setpoint command for an individual generator."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    genset_id: str
    target_state: bool = Field(description="True=Run, False=Stop")
    power_setpoint_kw: Annotated[float, Field(ge=0.0)]


class BatteryDispatchCommand(BaseModel):
    """Setpoint command for the battery power conversion system."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_power_kw: float = Field(description=">0 discharge, <0 charge, 0 idle")
    enable_heater: bool = False


class LoadControlCommand(BaseModel):
    """Load control setpoints per tier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tier: int
    allowed_power_kw: Annotated[float, Field(ge=0.0)]
    shed_power_kw: Annotated[float, Field(ge=0.0)]


class Action(BaseModel):
    """Actuator setpoints sent to the physical plant or digital twin."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime
    gensets: list[GensetDispatchCommand]
    battery: BatteryDispatchCommand
    loads: list[LoadControlCommand]
    aux_heating_setpoint_kw: Annotated[float, Field(ge=0.0, default=0.0)]
    deferrable_power_setpoint_kw: Annotated[float, Field(ge=0.0, default=0.0)]
    supervisor_override_active: bool = False
    override_reason: str | None = None
