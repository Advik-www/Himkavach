"""Station configuration contracts for HimKavach."""

from pydantic import BaseModel, ConfigDict, Field


class GensetConfig(BaseModel):
    """Specification of an individual diesel generator set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="Unique generator identifier")
    rated_power_kw: float = Field(gt=0, description="Nameplate rated electrical capacity in kW")
    min_load_ratio: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description="Minimum stable operating load as ratio of rated capacity",
    )
    fuel_intercept_l_per_h_kw: float = Field(
        default=0.08,
        ge=0.0,
        description="Fuel consumption intercept 'a' in L/h per kW rated (no-load burn)",
    )
    fuel_slope_l_per_h_kw: float = Field(
        default=0.25,
        ge=0.0,
        description="Marginal fuel consumption slope 'b' in L/h per kW electrical output",
    )
    min_uptime_min: int = Field(
        default=60, ge=0, description="Minimum run time once started (minutes)"
    )
    min_downtime_min: int = Field(
        default=30, ge=0, description="Minimum rest time once stopped (minutes)"
    )
    ramp_rate_kw_per_min: float = Field(
        default=30.0, gt=0, description="Maximum ramp rate (kW/min)"
    )
    start_cost_usd: float = Field(
        default=15.0, ge=0.0, description="Start-up wear and fuel crank cost penalty ($)"
    )
    cold_start_delay_min: int = Field(
        default=15,
        ge=0,
        description="Time delay before cold generator can accept full load (minutes)",
    )
    heat_recovery_efficiency: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Fraction of fuel thermal energy recoverable as useful heating",
    )

    @property
    def min_stable_power_kw(self) -> float:
        """Minimum stable output in kW."""
        return self.rated_power_kw * self.min_load_ratio


class BatteryConfig(BaseModel):
    """Specification of battery energy storage system."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(default="BESS_MAIN", description="Battery system identifier")
    capacity_kwh: float = Field(gt=0, description="Nominal usable storage capacity in kWh")
    max_charge_kw: float = Field(gt=0, description="Maximum charge rate in kW")
    max_discharge_kw: float = Field(gt=0, description="Maximum discharge rate in kW")
    charge_efficiency: float = Field(
        default=0.96, gt=0.0, le=1.0, description="One-way charging efficiency"
    )
    discharge_efficiency: float = Field(
        default=0.96, gt=0.0, le=1.0, description="One-way discharging efficiency"
    )
    min_soc: float = Field(
        default=0.10, ge=0.0, le=1.0, description="Minimum allowable State of Charge floor"
    )
    max_soc: float = Field(
        default=1.00, ge=0.0, le=1.0, description="Maximum allowable State of Charge ceiling"
    )
    min_temp_c_for_charging: float = Field(
        default=0.0, description="Minimum battery cell temperature for charging (°C)"
    )
    heater_power_kw: float = Field(
        default=5.0, ge=0.0, description="Electric enclosure heater consumption (kW)"
    )
    degradation_cost_per_kwh: float = Field(
        default=0.05,
        ge=0.0,
        description="Amortized cycle degradation cost per discharged kWh ($/kWh)",
    )

    @property
    def round_trip_efficiency(self) -> float:
        """Round-trip efficiency."""
        return self.charge_efficiency * self.discharge_efficiency


class WindTurbineConfig(BaseModel):
    """Specification of wind turbine unit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="Turbine identifier")
    rated_power_kw: float = Field(gt=0, description="Rated electrical power in kW")
    cut_in_speed_m_s: float = Field(default=3.0, gt=0, description="Cut-in wind speed (m/s)")
    rated_speed_m_s: float = Field(default=12.0, gt=0, description="Rated wind speed (m/s)")
    cut_out_speed_m_s: float = Field(
        default=25.0, gt=0, description="High-wind cut-out speed (m/s)"
    )
    restart_speed_m_s: float = Field(
        default=20.0, gt=0, description="Restart wind speed threshold below cut-out (m/s)"
    )
    restart_dwell_min: int = Field(
        default=10,
        ge=0,
        description="Required dwell time below restart speed before re-engaging (minutes)",
    )
    hub_height_m: float = Field(default=25.0, gt=0, description="Hub height in metres")
    icing_derate_factor: float = Field(
        default=0.85, ge=0.0, le=1.0, description="Power output multiplier under active rotor icing"
    )


class SolarPVConfig(BaseModel):
    """Specification of photovoltaic array."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="PV array identifier")
    peak_power_kw: float = Field(gt=0, description="Rated peak power under STC in kWp")
    tilt_deg: float = Field(
        default=65.0, ge=0.0, le=90.0, description="Array tilt angle from horizontal (deg)"
    )
    azimuth_deg: float = Field(
        default=0.0,
        ge=0.0,
        le=360.0,
        description="Azimuth angle: 0=North (Southern hemisphere facing equator)",
    )
    temp_coeff_per_c: float = Field(
        default=-0.0038, description="Temperature coefficient of power (%/°C / 100)"
    )
    snow_shed_temp_c: float = Field(
        default=-2.0, description="Temperature above which snow shedding accelerates (°C)"
    )


class ThermalConfig(BaseModel):
    """Thermal building mass and auxiliary heating parameters."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    building_heat_capacity_kwh_per_c: float = Field(
        default=150.0,
        gt=0,
        description="Effective lumped building thermal capacitance (kWh/°C)",
    )
    building_heat_loss_kw_per_c: float = Field(
        default=4.5, gt=0, description="Overall building thermal heat loss coefficient (kW/°C)"
    )
    min_temp_c: float = Field(
        default=16.0, description="Minimum acceptable indoor temperature (°C)"
    )
    max_temp_c: float = Field(
        default=24.0,
        description="Maximum indoor comfort temperature for thermal pre-heating (°C)",
    )
    setpoint_temp_c: float = Field(
        default=20.0, description="Target normal indoor setpoint temperature (°C)"
    )
    aux_heater_max_kw: float = Field(
        default=100.0, gt=0, description="Electric resistance backup heating capacity (kW)"
    )
    water_tank_capacity_l: float = Field(
        default=10000.0, gt=0, description="Potable snow-melt water tank volume (L)"
    )
    snow_melter_power_kw: float = Field(
        default=30.0, gt=0, description="Rated snow-melting electrical power (kW)"
    )


class LoadTierConfig(BaseModel):
    """Specification of a priority load tier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tier: int = Field(
        ge=0,
        le=3,
        description="0=Life Support, 1=Protected Science, 2=Comfort/Ops, 3=Deferrable",
    )
    name: str = Field(..., description="Descriptive tier name")
    base_kw: float = Field(ge=0, description="Typical baseline power in kW")
    peak_kw: float = Field(ge=0, description="Peak load in kW")
    ride_through_min: int = Field(
        default=0, ge=0, description="Maximum tolerable uninterrupted outage (minutes)"
    )
    max_daily_shed_hours: float = Field(
        default=0.0, ge=0, description="Maximum tolerable shed hours per 24 hours"
    )
    voll_usd_per_kwh: float = Field(gt=0, description="Value of Lost Load penalty ($/kWh)")


class FuelConfig(BaseModel):
    """Bulk diesel fuel inventory and resupply logistics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tank_capacity_l: float = Field(
        default=180000.0, gt=0, description="Total fuel storage capacity in litres"
    )
    initial_inventory_l: float = Field(
        default=150000.0, gt=0, description="Starting fuel volume in litres"
    )
    days_to_resupply: int = Field(
        default=300, gt=0, description="Nominal days until next annual resupply ship arrival"
    )
    contingency_days: int = Field(
        default=45, ge=0, description="Mandatory contingency fuel reserve in days"
    )
    fuel_unit_cost_usd_per_l: float = Field(
        default=2.20, gt=0, description="Delivered diesel cost per litre ($/L)"
    )


class StationConfig(BaseModel):
    """Top-level station configuration contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    station_id: str = Field(..., description="Unique station code, e.g. 'REFERENCE_MAITRI'")
    name: str = Field(..., description="Human-readable station name")
    latitude: float = Field(ge=-90.0, le=90.0, description="Geographic latitude in decimal degrees")
    longitude: float = Field(
        ge=-180.0, le=180.0, description="Geographic longitude in decimal degrees"
    )
    elevation_m: float = Field(default=100.0, ge=0.0, description="Altitude above sea level (m)")
    gensets: list[GensetConfig] = Field(..., min_length=1, description="List of generator sets")
    battery: BatteryConfig = Field(..., description="Battery energy storage system")
    wind_turbines: list[WindTurbineConfig] = Field(
        default_factory=list, description="Wind turbines"
    )
    pv_arrays: list[SolarPVConfig] = Field(default_factory=list, description="Solar PV arrays")
    thermal: ThermalConfig = Field(
        default_factory=ThermalConfig, description="Thermal building and storage model"
    )
    load_tiers: list[LoadTierConfig] = Field(
        ..., min_length=4, description="Load tiers 0 through 3"
    )
    fuel: FuelConfig = Field(default_factory=FuelConfig, description="Fuel logistics and storage")

    @property
    def total_genset_capacity_kw(self) -> float:
        """Total installed generator capacity."""
        return sum(g.rated_power_kw for g in self.gensets)

    @property
    def total_wind_capacity_kw(self) -> float:
        """Total installed wind capacity."""
        return sum(w.rated_power_kw for w in self.wind_turbines)

    @property
    def total_pv_capacity_kw(self) -> float:
        """Total installed solar PV capacity."""
        return sum(p.peak_power_kw for p in self.pv_arrays)

    def get_tier(self, tier_num: int) -> LoadTierConfig:
        """Fetch config for a specific load tier."""
        for lt in self.load_tiers:
            if lt.tier == tier_num:
                return lt
        raise KeyError(f"Load tier {tier_num} not defined")
