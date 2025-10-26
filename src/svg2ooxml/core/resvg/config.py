"""Configuration helpers for pyportresvg."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from .constants import FEATURE_FLAGS, FeatureFlag

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _parse_bool(value: str, *, flag: FeatureFlag) -> bool:
    value_lower = value.strip().lower()
    if value_lower in _TRUE_VALUES:
        return True
    if value_lower in _FALSE_VALUES:
        return False
    raise ValueError(
        f"Invalid value {value!r} for feature flag {flag.name!r}; "
        "expected one of: 1, 0, true, false, yes, no, on, off."
    )


def _env_key(flag_name: str) -> str:
    return f"PYPORTRESVG_FEATURE_{flag_name.replace('-', '_').upper()}"


@dataclass(frozen=True)
class Config:
    """Top-level configuration object produced from environment defaults."""

    feature_flags: dict[str, bool]

    def feature_enabled(self, flag_name: str) -> bool:
        try:
            return self.feature_flags[flag_name]
        except KeyError as exc:
            raise KeyError(f"Unknown feature flag {flag_name!r}") from exc


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Load configuration from environment variables."""
    env = env or os.environ
    flags: dict[str, bool] = {}

    for name, flag in FEATURE_FLAGS.items():
        key = _env_key(name)
        if key in env:
            flags[name] = _parse_bool(env[key], flag=flag)
        else:
            flags[name] = flag.default

    return Config(feature_flags=flags)


DEFAULT_CONFIG = load_config({})
