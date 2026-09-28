"""Evaluation and operational metrics contracts."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class TierUnmetMetrics(BaseModel):
    """Unserved energy metrics for a specific priority load tier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tier: int
    unmet_energy_kwh: Annotated[float, Field(ge=0.0)]
    unmet_hours: Annotated[float, Field(ge=0.0)]
    interruption_events_count: Annotated[int, Field(ge=0)]


class Metrics(BaseModel):
    """Standardized performance metrics across all simulation episodes and baselines."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_fuel_consumed_l: Annotated[float, Field(ge=0.0)]
    specific_fuel_consumption_l_per_mwh: Annotated[float, Field(ge=0.0)]
    total_energy_served_kwh: Annotated[float, Field(ge=0.0)]
    renewable_energy_generated_kwh: Annotated[float, Field(ge=0.0)]
    renewable_energy_curtailed_kwh: Annotated[float, Field(ge=0.0)]
    renewable_penetration_pct: Annotated[float, Field(ge=0.0, le=100.0)]
    battery_equivalent_full_cycles: Annotated[float, Field(ge=0.0)]
    battery_total_throughput_kwh: Annotated[float, Field(ge=0.0)]
    battery_min_soc: Annotated[float, Field(ge=0.0, le=1.0)]
    battery_mean_soc: Annotated[float, Field(ge=0.0, le=1.0)]
    battery_hours_below_20pct_soc: Annotated[float, Field(ge=0.0)]
    tier_unmet: list[TierUnmetMetrics]
    generator_total_starts: Annotated[int, Field(ge=0)]
    generator_total_runtime_hours: Annotated[float, Field(ge=0.0)]
    co2_emissions_kg: Annotated[float, Field(ge=0.0)]
    total_operating_cost_usd: Annotated[float, Field(ge=0.0)]
    min_survival_hours_observed: Annotated[float, Field(ge=0.0)]
    min_glide_path_margin_l: float
    mean_solve_time_sec: Annotated[float, Field(ge=0.0, default=0.0)]
    p95_solve_time_sec: Annotated[float, Field(ge=0.0, default=0.0)]
    supervisor_overrides_count: Annotated[int, Field(ge=0, default=0)]

    @property
    def tier0_unmet_kwh(self) -> float:
        for tu in self.tier_unmet:
            if tu.tier == 0:
                return tu.unmet_energy_kwh
        return 0.0

    @property
    def tier1_unmet_kwh(self) -> float:
        for tu in self.tier_unmet:
            if tu.tier == 1:
                return tu.unmet_energy_kwh
        return 0.0
