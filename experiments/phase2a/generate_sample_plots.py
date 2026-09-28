"""Sample-day plot generator for Phase 2A Digital Twin validation.

Simulates and plots one Antarctic winter day (polar night, high wind, severe cold)
and one Antarctic summer day (continuous sun, moderate cold, PV active) showing:
1. Synthetic Weather (Temperature, Wind Speed, Solar Irradiance)
2. Renewable & Diesel Generation (PV, Wind Turbines, Genset dispatch)
3. Tiered Electrical Loads (T0 life support, T1 science, T2 comfort, T3 deferrable)
4. Energy Storage Dynamics (Battery SoC, Charge/Discharge Power, Cell Temperature)
5. Station Thermal Dynamics (Indoor Temp, Waste Heat Recovery)

Outputs high-resolution publication-quality figures to experiments/phase2a/.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure packages are discoverable when run directly
workspace_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(workspace_root / "packages" / "core" / "src"))
sys.path.insert(0, str(workspace_root / "packages" / "twin" / "src"))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from himkavach_core.config_loader import load_station_config  # noqa: E402
from himkavach_twin.battery import BatteryModel  # noqa: E402
from himkavach_twin.fuel_tank import FuelTankModel  # noqa: E402
from himkavach_twin.genset import GensetModel  # noqa: E402
from himkavach_twin.loads import LoadModel, ThermalModel  # noqa: E402
from himkavach_twin.solar import SolarPVModel  # noqa: E402
from himkavach_twin.weather_synth import generate_synthetic_weather  # noqa: E402
from himkavach_twin.wind import WindTurbineModel  # noqa: E402


def simulate_day(
    station_config_path: Path,
    start_date: datetime,
    seed: int,
) -> dict[str, np.ndarray]:
    """Run a 24-hour simulation using all plant twin models."""
    cfg = load_station_config(station_config_path)
    rng = np.random.default_rng(seed)

    # 1. Weather
    weather = generate_synthetic_weather(
        latitude=cfg.latitude,
        longitude=cfg.longitude,
        start=start_date,
        hours=24,
        rng=rng,
        winter_mean_temp_c=-30.0,
        summer_mean_temp_c=-4.0,
        mean_wind_m_s=9.5,
    )

    # 2. Plant components
    pv = SolarPVModel(cfg.pv_arrays[0], latitude=cfg.latitude, longitude=cfg.longitude)
    turbines = [WindTurbineModel(wt_cfg) for wt_cfg in cfg.wind_turbines]
    battery = BatteryModel(cfg.battery, initial_soc=0.65)
    genset = GensetModel(cfg.gensets[0])
    fuel_tank = FuelTankModel(cfg.fuel)
    thermal = ThermalModel(cfg.thermal, initial_indoor_temp_c=20.0)
    load_model = LoadModel(cfg.load_tiers, rng=rng)

    hours = np.arange(24)
    data = {
        "hour": hours,
        "temp_amb": np.zeros(24),
        "wind_speed": np.zeros(24),
        "ghi": np.zeros(24),
        "pv_kw": np.zeros(24),
        "wind_kw": np.zeros(24),
        "load_t0": np.zeros(24),
        "load_t1": np.zeros(24),
        "load_t2": np.zeros(24),
        "load_t3": np.zeros(24),
        "load_total": np.zeros(24),
        "genset_kw": np.zeros(24),
        "fuel_rate": np.zeros(24),
        "waste_heat_kw": np.zeros(24),
        "bat_p_kw": np.zeros(24),
        "bat_soc": np.zeros(24),
        "bat_temp": np.zeros(24),
        "indoor_temp": np.zeros(24),
    }

    for h, w in enumerate(weather):
        data["temp_amb"][h] = w.temperature_c
        data["wind_speed"][h] = w.wind_speed_m_s
        data["ghi"][h] = w.ghi_w_m2

        # Generation
        pv_step = pv.step(w, dt_hours=1.0)
        data["pv_kw"][h] = pv_step["power_kw"]

        total_wind = 0.0
        for turb in turbines:
            w_step = turb.step(
                wind_speed_m_s=w.wind_speed_m_s,
                temperature_c=w.temperature_c,
                pressure_hpa=w.surface_pressure_hpa,
                is_icing=w.is_icing_risk,
                dt_hours=1.0,
            )
            total_wind += w_step["power_kw"]
        data["wind_kw"][h] = total_wind

        # Loads
        loads = load_model.generate_loads(
            hour_of_day=h,
            day_of_year=w.timestamp.timetuple().tm_yday,
            ambient_temp_c=w.temperature_c,
            wind_speed_m_s=w.wind_speed_m_s,
        )
        data["load_t0"][h] = loads[0]
        data["load_t1"][h] = loads[1]
        data["load_t2"][h] = loads[2]
        data["load_t3"][h] = loads[3]
        total_load = sum(loads.values())
        data["load_total"][h] = total_load

        # Heuristic dispatch for demonstration
        re_gen = data["pv_kw"][h] + data["wind_kw"][h]
        net_demand = total_load - re_gen

        if net_demand < 0:
            # Excess renewables: charge battery
            bat_setpoint = max(net_demand, -cfg.battery.max_charge_kw)
            gen_target = False
            gen_p = 0.0
        else:
            # Deficit: discharge battery up to 120 kW, remainder to genset
            bat_setpoint = min(net_demand, 120.0)
            unmet = net_demand - bat_setpoint
            if unmet > 20.0:
                gen_target = True
                gen_p = unmet
            else:
                gen_target = False
                gen_p = 0.0

        bat_step = battery.step(bat_setpoint, ambient_temp_c=w.temperature_c, dt_hours=1.0)
        data["bat_p_kw"][h] = bat_step["actual_power_kw"]
        data["bat_soc"][h] = bat_step["soc"] * 100.0
        data["bat_temp"][h] = bat_step["cell_temp_c"]

        gen_step = genset.step(gen_target, gen_p, ambient_temp_c=w.temperature_c, dt_hours=1.0)
        data["genset_kw"][h] = gen_step["power_kw"]
        data["fuel_rate"][h] = gen_step["fuel_rate_l_per_h"]
        data["waste_heat_kw"][h] = gen_step["waste_heat_kw"]

        fuel_tank.step(gen_step["fuel_consumed_l"], dt_hours=1.0)

        # Thermal
        therm_step = thermal.step(
            ambient_temp_c=w.temperature_c,
            wind_speed_m_s=w.wind_speed_m_s,
            waste_heat_kw=gen_step["waste_heat_kw"],
            aux_heating_kw=15.0 if w.temperature_c < -25.0 else 0.0,
            internal_gains_kw=8.0,
            dt_hours=1.0,
        )
        data["indoor_temp"][h] = therm_step["indoor_temp_c"]

    return data


def plot_single_day(data: dict[str, np.ndarray], title: str, output_path: Path) -> None:
    """Generate a clean 4-panel dashboard for a 24-hour polar day."""
    fig, axes = plt.subplots(4, 1, figsize=(12, 14), sharex=True)
    hours = data["hour"]

    # 1. Weather panel
    ax0 = axes[0]
    ax0_twin = ax0.twinx()
    l1 = ax0.plot(
        hours, data["temp_amb"], "tab:blue", marker="o", label="Ambient Temp (°C)", linewidth=2
    )
    l2 = ax0.plot(
        hours,
        data["wind_speed"],
        "tab:cyan",
        linestyle="--",
        label="Wind Speed (m/s)",
        linewidth=1.8,
    )
    l3 = ax0_twin.plot(hours, data["ghi"], "tab:orange", label="GHI Irradiance (W/m²)", linewidth=2)
    ax0.set_ylabel("Temp (°C) / Wind (m/s)", color="tab:blue")
    ax0_twin.set_ylabel("GHI (W/m²)", color="tab:orange")
    ax0.set_title(f"{title} — Environmental Conditions", fontsize=12, fontweight="bold")
    ax0.grid(True, alpha=0.3)
    lines = l1 + l2 + l3
    labels = [line_obj.get_label() for line_obj in lines]
    ax0.legend(lines, labels, loc="upper right", framealpha=0.85)

    # 2. Generation vs Load panel
    ax1 = axes[1]
    ax1.plot(hours, data["pv_kw"], color="gold", label="Solar PV (kW)", linewidth=2)
    ax1.plot(hours, data["wind_kw"], color="teal", label="Wind Turbines (kW)", linewidth=2)
    ax1.plot(
        hours,
        data["genset_kw"],
        color="crimson",
        linestyle="-.",
        label="Diesel Genset (kW)",
        linewidth=2,
    )
    ax1.plot(
        hours,
        data["load_total"],
        color="black",
        linestyle="--",
        label="Total Station Load (kW)",
        linewidth=2.5,
    )
    ax1.set_ylabel("Power (kW)")
    ax1.set_title("Power Dispatch & Generation vs Total Demand", fontsize=12, fontweight="bold")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper right", framealpha=0.85)

    # 3. Load Breakdown panel
    ax2 = axes[2]
    ax2.stackplot(
        hours,
        data["load_t0"],
        data["load_t1"],
        data["load_t2"],
        data["load_t3"],
        labels=["T0: Life Support", "T1: Science", "T2: Comfort/Galley", "T3: Deferrable Melter"],
        colors=["#d62728", "#1f77b4", "#2ca02c", "#9467bd"],
        alpha=0.85,
    )
    ax2.set_ylabel("Load (kW)")
    ax2.set_title("Tiered Electrical Load Demand", fontsize=12, fontweight="bold")
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="upper right", framealpha=0.85)

    # 4. Storage & Thermal panel
    ax3 = axes[3]
    ax3_twin = ax3.twinx()
    l_soc = ax3.plot(
        hours,
        data["bat_soc"],
        color="purple",
        marker="s",
        markersize=4,
        label="Battery SoC (%)",
        linewidth=2,
    )
    l_tin = ax3_twin.plot(
        hours, data["indoor_temp"], color="darkgreen", label="Indoor Habitat Temp (°C)", linewidth=2
    )
    l_gen_heat = ax3_twin.plot(
        hours,
        data["waste_heat_kw"],
        color="coral",
        linestyle=":",
        label="Recovered Waste Heat (kW_th)",
        linewidth=1.8,
    )
    ax3.set_ylabel("Battery SoC (%)", color="purple")
    ax3.set_ylim(0, 105)
    ax3_twin.set_ylabel("Temperature (°C) / Heat (kW_th)", color="darkgreen")
    ax3.set_xlabel("Hour of Day (UTC)", fontsize=11, fontweight="bold")
    ax3.set_title(
        "Battery State of Charge & Station Habitat Thermal State", fontsize=12, fontweight="bold"
    )
    ax3.grid(True, alpha=0.3)
    lines_b = l_soc + l_tin + l_gen_heat
    labels_b = [line_obj.get_label() for line_obj in lines_b]
    ax3.legend(lines_b, labels_b, loc="upper right", framealpha=0.85)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def generate_all_sample_plots() -> None:
    """Generate both winter and summer sample days and a combined comparison."""
    config_path = Path("configs/stations/reference.yaml")
    out_dir = Path("experiments/phase2a")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Simulating Antarctic Winter Day (July 15, polar night)...")
    winter_date = datetime(2026, 7, 15, 0, 0, tzinfo=UTC)
    winter_data = simulate_day(config_path, winter_date, seed=42)
    winter_plot_path = out_dir / "winter_day.png"
    plot_single_day(winter_data, "Antarctic Winter Day (July 15 — Polar Night)", winter_plot_path)
    print(f"Saved: {winter_plot_path}")

    print("Simulating Antarctic Summer Day (January 15, continuous sunlight)...")
    summer_date = datetime(2026, 1, 15, 0, 0, tzinfo=UTC)
    summer_data = simulate_day(config_path, summer_date, seed=101)
    summer_plot_path = out_dir / "summer_day.png"
    plot_single_day(summer_data, "Antarctic Summer Day (January 15 — Polar Day)", summer_plot_path)
    print(f"Saved: {summer_plot_path}")

    # Generate combined 2-column comparative plot
    print("Generating comparative figure...")
    fig, axes = plt.subplots(3, 2, figsize=(16, 12), sharex=True)

    # Col 0: Winter, Col 1: Summer
    for col, (day_data, day_name, season_color) in enumerate(
        [
            (winter_data, "Winter (July 15)", "navy"),
            (summer_data, "Summer (January 15)", "darkorange"),
        ]
    ):
        h = day_data["hour"]

        # Row 0: Weather
        ax0 = axes[0, col]
        ax0_t = ax0.twinx()
        ax0.plot(h, day_data["temp_amb"], "blue", label="Temp (°C)", linewidth=2)
        ax0.plot(
            h, day_data["wind_speed"], "cyan", linestyle="--", label="Wind (m/s)", linewidth=1.5
        )
        ax0_t.plot(h, day_data["ghi"], "orange", label="GHI (W/m²)", linewidth=2)
        ax0.set_title(f"{day_name} — Weather", fontsize=11, fontweight="bold", color=season_color)
        ax0.set_ylabel("Temp (°C) / Wind (m/s)")
        ax0_t.set_ylabel("GHI (W/m²)")
        ax0.grid(True, alpha=0.3)
        if col == 0:
            ax0.legend(loc="upper left")

        # Row 1: Generation & Load
        ax1 = axes[1, col]
        ax1.plot(h, day_data["pv_kw"], color="gold", label="PV (kW)", linewidth=2)
        ax1.plot(h, day_data["wind_kw"], color="teal", label="Wind (kW)", linewidth=2)
        ax1.plot(
            h,
            day_data["genset_kw"],
            color="crimson",
            linestyle="-.",
            label="Genset (kW)",
            linewidth=2,
        )
        ax1.plot(
            h, day_data["load_total"], color="black", linestyle="--", label="Load (kW)", linewidth=2
        )
        ax1.set_title(f"{day_name} — Generation & Dispatch", fontsize=11, fontweight="bold")
        ax1.set_ylabel("Power (kW)")
        ax1.grid(True, alpha=0.3)
        if col == 0:
            ax1.legend(loc="upper left")

        # Row 2: Battery SoC & Habitat Temp
        ax2 = axes[2, col]
        ax2_t = ax2.twinx()
        ax2.plot(h, day_data["bat_soc"], color="purple", label="Battery SoC (%)", linewidth=2)
        ax2_t.plot(h, day_data["indoor_temp"], color="green", label="Indoor Temp (°C)", linewidth=2)
        ax2.set_title(f"{day_name} — Battery SoC & Indoor Temp", fontsize=11, fontweight="bold")
        ax2.set_xlabel("Hour (UTC)", fontweight="bold")
        ax2.set_ylabel("Battery SoC (%)")
        ax2.set_ylim(0, 105)
        ax2_t.set_ylabel("Indoor Temp (°C)")
        ax2.grid(True, alpha=0.3)
        if col == 0:
            ax2.legend(loc="upper left")

    plt.suptitle(
        "HimKavach Digital Twin — Polar Station Operational Profiles",
        fontsize=14,
        fontweight="bold",
    )
    plt.tight_layout()
    comparison_path = out_dir / "sample_days_comparison.png"
    fig.savefig(comparison_path, dpi=200)
    plt.close(fig)
    print(f"Saved: {comparison_path}")


if __name__ == "__main__":
    generate_all_sample_plots()
