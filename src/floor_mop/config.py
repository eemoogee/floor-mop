"""Layered configuration loader for Floor Mop."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, NonNegativeInt, PositiveInt, ValidationError

_ENV_PREFIX = "FLOOR_MOP__"


class ConfigError(Exception):
    """Raised for any configuration loading or validation failure."""


class LoggingConfig(BaseModel):
    """Logging configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    dir: Path
    max_bytes: PositiveInt
    backup_count: NonNegativeInt
    console: bool


class PathsConfig(BaseModel):
    """Filesystem path configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    data_dir: Path


class Settings(BaseModel):
    """Top-level application settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    logging: LoggingConfig
    paths: PathsConfig


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base, returning a new dict."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_toml(path: Path) -> dict[str, Any]:
    """Parse a TOML file, raising ConfigError on failure."""
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Malformed TOML in {path}: {exc}") from None


def _env_overrides(env: Mapping[str, str]) -> dict[str, Any]:
    """Build a nested override dict from FLOOR_MOP__-prefixed env vars."""
    overrides: dict[str, Any] = {}
    for name, value in env.items():
        if not name.startswith(_ENV_PREFIX):
            continue
        path = [part.lower() for part in name[len(_ENV_PREFIX) :].split("__")]
        node = overrides
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = value
    return overrides


def _format_validation_error(exc: ValidationError) -> str:
    """Render a ValidationError without leaking any offending input values."""
    lines = []
    for error in exc.errors(include_input=False, include_url=False):
        loc = ".".join(str(part) for part in error["loc"])
        lines.append(f"{loc}: {error['msg']}")
    return "; ".join(lines)


def load_settings(
    config_dir: Path | None = None, env: Mapping[str, str] | None = None
) -> Settings:
    """Load Settings by layering default.toml, local.toml, and environment variables."""
    if env is None:
        env = os.environ

    if config_dir is None:
        env_dir = env.get("FLOOR_MOP_CONFIG_DIR")
        config_dir = Path(env_dir) if env_dir is not None else Path("config")

    default_path = config_dir / "default.toml"
    if not default_path.is_file():
        raise ConfigError(f"Required configuration file not found: {default_path}")
    merged = _load_toml(default_path)

    local_path = config_dir / "local.toml"
    if local_path.is_file():
        merged = _deep_merge(merged, _load_toml(local_path))

    merged = _deep_merge(merged, _env_overrides(env))

    try:
        return Settings.model_validate(merged)
    except ValidationError as exc:
        raise ConfigError(
            f"Invalid configuration: {_format_validation_error(exc)}"
        ) from None
