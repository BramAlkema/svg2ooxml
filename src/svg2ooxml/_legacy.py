"""Helpers for bridging svg2pptx-era packages under ``svg2ooxml.legacy``.

The svg2ooxml project is gradually porting code from the older svg2pptx
repository. During the transition many modules still live under a
``legacy`` namespace. This helper allows lightweight compatibility
packages such as ``svg2ooxml.paint`` to delegate to the legacy module
tree without eager imports scattered across the codebase.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Final
import sys

_LEGACY_PREFIX: Final[str] = "svg2ooxml.legacy."


def redirect_package(package_name: str) -> ModuleType:
    """Return the legacy module for ``package_name`` and register it."""

    legacy_module = import_module(f"{_LEGACY_PREFIX}{package_name}")
    sys.modules[f"svg2ooxml.{package_name}"] = legacy_module
    return legacy_module


__all__ = ["redirect_package"]
