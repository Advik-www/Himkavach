"""Unit tests for configuration loaders."""

from pathlib import Path

import pytest
from himkavach_core.config_loader import load_experiment_config, load_station_config, load_yaml


def test_load_reference_station_yaml() -> None:
    ref_path = Path("configs/stations/reference.yaml")
    assert ref_path.exists(), f"Reference config missing at {ref_path.resolve()}"

    config = load_station_config(ref_path)
    assert config.station_id == "REFERENCE_ANTARCTIC_STATION"
    assert len(config.gensets) == 3
    assert config.battery.capacity_kwh == 600.0
    assert len(config.wind_turbines) == 2
    assert len(config.pv_arrays) == 1
    assert len(config.load_tiers) == 4
    assert config.fuel.tank_capacity_l == 180000.0
    assert config.fuel.contingency_days == 45


def test_load_storm_night_experiment_yaml() -> None:
    exp_path = Path("configs/experiments/storm_night.yaml")
    assert exp_path.exists(), f"Experiment config missing at {exp_path.resolve()}"

    config = load_experiment_config(exp_path)
    assert config.experiment_id == "EXP_STORM_NIGHT_72H"
    assert config.duration_hours == 72.0
    assert config.seed == 42
    assert len(config.injected_faults) == 1
    assert config.injected_faults[0].fault_type == "GENSET_TRIP"


def test_missing_file_raises_error() -> None:
    with pytest.raises(FileNotFoundError):
        load_yaml("non_existent_file.yaml")


def test_invalid_station_config_raises_error(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad_station.yaml"
    # missing required battery and load_tiers
    bad_yaml.write_text(
        "station_id: BAD\nname: Incomplete Station\nlatitude: 0\nlongitude: 0\ngensets: []\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Station configuration validation error"):
        load_station_config(bad_yaml)
