"""Configuration loading and validation utility for HimKavach."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from himkavach_core.contracts.experiment import ExperimentConfig
from himkavach_core.contracts.station import StationConfig


def load_yaml(file_path: str | Path) -> dict[str, Any]:
    """Safely parse a YAML configuration file into a dictionary."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path.resolve()}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML content in {path} must be a dictionary, got {type(data).__name__}")
    return data


def load_station_config(file_path: str | Path) -> StationConfig:
    """Load and strictly validate a StationConfig YAML."""
    raw = load_yaml(file_path)
    try:
        return StationConfig.model_validate(raw)
    except ValidationError as err:
        raise ValueError(f"Station configuration validation error in {file_path}:\n{err}") from err


def load_experiment_config(file_path: str | Path) -> ExperimentConfig:
    """Load and strictly validate an ExperimentConfig YAML."""
    raw = load_yaml(file_path)
    try:
        return ExperimentConfig.model_validate(raw)
    except ValidationError as err:
        raise ValueError(
            f"Experiment configuration validation error in {file_path}:\n{err}"
        ) from err
