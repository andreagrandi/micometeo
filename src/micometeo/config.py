"""Experiment settings read from config.toml."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_TIME_LIMIT_MINUTES = 30
DEFAULT_TIME_LIMIT_MINUTES = 30


class ConfigError(ValueError):
    """Raised when an experiment config is not valid."""


@dataclass(frozen=True)
class ExperimentConfig:
    """Validated contents of a config.toml file."""

    description: str
    seed: int
    time_limit_minutes: float
    settings: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return the config as a plain dict for the run record."""
        return {
            "description": self.description,
            "seed": self.seed,
            "time_limit_minutes": self.time_limit_minutes,
            "settings": self.settings,
        }


def load_config(*, path: Path) -> ExperimentConfig:
    """Read and check a config.toml file."""
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    seed = raw.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ConfigError(f"{path}: 'seed' is required and must be an integer")
    limit = raw.get("time_limit_minutes", DEFAULT_TIME_LIMIT_MINUTES)
    if isinstance(limit, bool) or not isinstance(limit, (int, float)):
        raise ConfigError(f"{path}: 'time_limit_minutes' must be a number")
    if limit <= 0:
        raise ConfigError(f"{path}: 'time_limit_minutes' must be above 0")
    if limit > MAX_TIME_LIMIT_MINUTES:
        raise ConfigError(
            f"{path}: 'time_limit_minutes' is {limit}, "
            f"the maximum is {MAX_TIME_LIMIT_MINUTES}"
        )
    settings = raw.get("settings", {})
    if not isinstance(settings, dict):
        raise ConfigError(f"{path}: 'settings' must be a table")
    return ExperimentConfig(
        description=str(raw.get("description", "")),
        seed=seed,
        time_limit_minutes=limit,
        settings=settings,
    )
