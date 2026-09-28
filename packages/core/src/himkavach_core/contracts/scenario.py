"""Correlated weather scenario contracts for stochastic MPC."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScenarioStep(BaseModel):
    """Scenario realization at a single time step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    step_index: int
    timestamp: datetime
    duration_hours: Annotated[float, Field(gt=0.0)]
    wind_avail_kw: Annotated[float, Field(ge=0.0)]
    solar_avail_kw: Annotated[float, Field(ge=0.0)]
    ambient_temp_c: float
    load_tier0_kw: Annotated[float, Field(ge=0.0)]
    load_tier1_kw: Annotated[float, Field(ge=0.0)]
    load_tier2_kw: Annotated[float, Field(ge=0.0)]
    load_tier3_kw: Annotated[float, Field(ge=0.0)]
    is_wind_cutout: bool = False
    is_rotor_iced: bool = False


class Scenario(BaseModel):
    """A single physically coherent future realization trajectory across the horizon."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: str
    probability: Annotated[float, Field(ge=0.0, le=1.0)]
    is_stress_case: bool = False
    steps: list[ScenarioStep] = Field(..., min_length=1)

    @property
    def total_steps(self) -> int:
        return len(self.steps)


class ScenarioSet(BaseModel):
    """Reduced representative scenario tree input to the stochastic MPC."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    set_id: str
    created_at: datetime
    scenarios: list[Scenario] = Field(..., min_length=1)
    stress_scenario_id: str | None = None

    @model_validator(mode="after")
    def validate_probabilities_sum(self) -> "ScenarioSet":
        total_p = sum(s.probability for s in self.scenarios)
        if not (0.99 <= total_p <= 1.01):
            raise ValueError(f"Scenario probabilities must sum to 1.0; got {total_p:.4f}")
        return self

    @property
    def count(self) -> int:
        return len(self.scenarios)
