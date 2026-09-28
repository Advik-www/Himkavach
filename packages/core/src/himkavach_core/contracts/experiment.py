"""Experiment runner configuration and result contracts."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from himkavach_core.contracts.metrics import Metrics


class FaultInjectionConfig(BaseModel):
    """Specification of an injected disturbance or equipment failure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fault_type: str = Field(
        description="GENSET_TRIP, SENSOR_DRIFT, BATTERY_STRING_LOSS, DEMAND_SPIKE, FUEL_LEAK"
    )
    target_id: str = Field(description="ID of target component")
    start_hour: Annotated[float, Field(ge=0.0)]
    duration_hours: Annotated[float, Field(gt=0.0)]
    magnitude: float = Field(default=1.0)


class ExperimentConfig(BaseModel):
    """Deterministic, reproducible experiment definition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_id: str
    name: str
    description: str
    station_config_path: str
    seed: int = 42
    duration_hours: Annotated[float, Field(gt=0.0, default=72.0)]
    weather_regime: str = Field(default="STORM_NIGHT_CYCLONE")
    controllers_to_run: list[str] = Field(
        default=["B1_NAIVE", "B2_TUNED_RULES", "B3_DETERMINISTIC_MPC", "B4_ORACLE", "HIMKAVACH"]
    )
    injected_faults: list[FaultInjectionConfig] = Field(default_factory=list)
    monte_carlo_samples: Annotated[int, Field(ge=1, default=1)]


class ControllerRunResult(BaseModel):
    """Result of a single controller execution over an episode."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    controller_id: str
    metrics: Metrics
    telemetry_parquet_path: str | None = None
    plan_log_path: str | None = None


class ExperimentResult(BaseModel):
    """Stored aggregate result of an experiment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_id: str
    timestamp: datetime
    config: ExperimentConfig
    controller_results: dict[str, ControllerRunResult]
    fuel_savings_waterfall: dict[str, float] = Field(
        default_factory=dict,
        description="Waterfall attribution: load_point, curtailment, pre_charge, thermal_shift",
    )
