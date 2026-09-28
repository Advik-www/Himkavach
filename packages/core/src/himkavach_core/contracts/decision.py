"""Explainable decision cards and operating level contracts."""

from datetime import datetime
from enum import IntEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class OperatingLevel(IntEnum):
    """Hierarchical station operating levels with hysteresis."""

    NORMAL = 0
    PRE_STORM = 1
    CONSERVE = 2
    SURVIVAL = 3
    LIFEBOAT = 4


class DecisionFactor(BaseModel):
    """Individual telemetry or forecast trigger driving an operating decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    factor_name: str
    observed_value: float
    threshold_value: float
    unit: str
    description: str


class CounterfactualEstimate(BaseModel):
    """Counterfactual outcome if alternative rule baseline B2 had been run instead."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline_policy: str = "B2_TUNED_RULES"
    fuel_delta_litres: float = Field(
        description="Fuel saved by HimKavach (>0) or extra fuel burned (<0)"
    )
    risk_delta_cvar_pct: float = Field(description="Reduction in tail-risk CVaR percentage")
    narrative: str


class DecisionCard(BaseModel):
    """Structured, human-readable operational decision card."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    card_id: str
    timestamp: datetime
    level: OperatingLevel
    level_name: str
    headline: str
    detailed_rationale: str
    trigger_factors: list[DecisionFactor]
    storm_probability_next_12h: Annotated[float, Field(ge=0.0, le=1.0)]
    recommended_actions: list[str]
    counterfactual: CounterfactualEstimate
    confidence_score: Annotated[float, Field(ge=0.0, le=1.0, default=0.95)]
