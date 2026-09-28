"""Subsystem health, drift, and anomaly contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class HealthStatus(StrEnum):
    """Subsystem operational health rating."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    FAILED = "FAILED"


class AnomalyEvent(BaseModel):
    """Specific detected anomaly from residual CUSUM or Isolation Forest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    anomaly_id: str
    detected_at: datetime
    subsystem: str
    anomaly_type: str = Field(
        description="GENSET_DRIFT, FUEL_DISCREPANCY, SENSOR_FAULT, ICING, SNOW_COVER"
    )
    severity: HealthStatus
    metric_name: str
    observed_value: float
    expected_value: float
    z_score_or_residual: float
    is_actionable: bool = True
    mitigation_applied: str | None = None


class HealthReport(BaseModel):
    """Periodic health summary fed back to optimizer and supervisor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    station_id: str
    timestamp: datetime
    overall_status: HealthStatus
    fuel_balance_mismatch_l: float = Field(
        description="Tank sensor drop vs expected integrated fuel burn (L)"
    )
    genset_efficiency_drift: dict[str, float] = Field(
        default_factory=dict, description="Observed vs nominal fuel rate ratio per genset"
    )
    wind_icing_detected: bool = False
    pv_snow_occlusion_ratio: Annotated[float, Field(ge=0.0, le=1.0, default=0.0)]
    active_anomalies: list[AnomalyEvent] = Field(default_factory=list)
