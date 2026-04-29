"""Shared helpers for policy provider payload parsing."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def normalise_quality(
    value: Any,
    fallbacks: Mapping[str, Any],
    *,
    default: str = "balanced",
) -> str:
    """Return a supported quality token for a provider fallback table."""

    if isinstance(value, str):
        token = value.strip().lower()
        if token in fallbacks:
            return token
    return default


def target_defaults(
    options: Mapping[str, Any],
    *,
    target_name: str,
    quality: str,
    fallbacks: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Resolve provider defaults from ``targets`` or the quality fallback table."""

    targets = options.get("targets")
    if isinstance(targets, Mapping):
        candidate = targets.get(target_name)
        if isinstance(candidate, Mapping):
            return dict(candidate)
    return dict(fallbacks.get(quality, fallbacks["balanced"]))


def dotted_overrides(
    options: Mapping[str, Any],
    *,
    prefix: str,
    coerce: Callable[[str, Any], Any] | None = None,
) -> dict[str, Any]:
    """Collect ``prefix.field`` options into a flat override payload."""

    overrides: dict[str, Any] = {}
    expected_prefix = prefix.strip(".")
    for key, raw in options.items():
        if not isinstance(key, str) or "." not in key:
            continue
        key_prefix, field = key.split(".", 1)
        if key_prefix != expected_prefix or not field:
            continue
        overrides[field] = coerce(field, raw) if coerce is not None else raw
    return overrides


__all__ = ["dotted_overrides", "normalise_quality", "target_defaults"]
