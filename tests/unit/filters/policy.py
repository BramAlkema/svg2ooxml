"""Shared filter test policy helpers.

Set SVG2OOXML_FILTER_POLICY=modern|legacy to switch expected fallbacks.
Set SVG2OOXML_FILTER_POLICY_STRICT=0 to allow broader fallbacks.
"""

from __future__ import annotations

import os
from typing import Iterable


def _policy_mode() -> str:
    mode = os.environ.get("SVG2OOXML_FILTER_POLICY", "modern").strip().lower()
    if mode in {"legacy", "emf"}:
        return "legacy"
    return "modern"


def _strict_mode() -> bool:
    token = os.environ.get("SVG2OOXML_FILTER_POLICY_STRICT", "1").strip().lower()
    return token not in {"0", "false", "no", "off"}


def _select(modern, legacy):
    if _policy_mode() == "legacy" and legacy is not None:
        return legacy
    return modern


def _as_set(value) -> set:
    if isinstance(value, (set, list, tuple)):
        return set(value)
    return {value}


def assert_fallback(obj, *, modern, legacy=None, allow=None) -> None:
    expected = _select(modern, legacy)
    if allow is not None and not _strict_mode():
        expected = _as_set(expected) | _as_set(allow)
    if isinstance(expected, (set, list, tuple)):
        assert obj.fallback in expected
    else:
        assert obj.fallback == expected


def assert_strategy(obj, *, modern, legacy=None, allow=None) -> None:
    expected = _select(modern, legacy)
    if allow is not None and not _strict_mode():
        expected = _as_set(expected) | _as_set(allow)
    if isinstance(expected, (set, list, tuple)):
        assert obj.strategy in expected
    else:
        assert obj.strategy == expected


def assert_assets(
    obj,
    *,
    modern: str | Iterable[str] | None,
    legacy: str | Iterable[str] | None = None,
    allow_empty: bool = False,
) -> None:
    expected = _select(modern, legacy)
    assets = getattr(obj, "metadata", {}).get("fallback_assets") if getattr(obj, "metadata", None) else None
    if not assets:
        assert allow_empty
        return
    types = {asset.get("type") for asset in assets if isinstance(asset, dict)}
    if expected is None:
        assert not types
        return
    expected_set = _as_set(expected)
    assert types & expected_set


def assert_no_assets(obj) -> None:
    assets = getattr(obj, "metadata", {}).get("fallback_assets") if getattr(obj, "metadata", None) else None
    assert not assets
