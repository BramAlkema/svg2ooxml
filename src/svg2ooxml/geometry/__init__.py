
"""Geometry helpers surfaced from ``svg2ooxml.common.geometry``."""

from __future__ import annotations

from importlib import import_module
import sys
from types import ModuleType

_COMMON_PREFIX = "svg2ooxml.common.geometry"


def _expose(name: str) -> ModuleType:
    module = import_module(f"{_COMMON_PREFIX}.{name}")
    sys.modules.setdefault(f"svg2ooxml.geometry.{name}", module)
    return module


algorithms = _expose("algorithms")
fractional = _expose("fractional")
paths = _expose("paths")
transforms = _expose("transforms")
matrix = import_module(f"{_COMMON_PREFIX}.matrix")
sys.modules.setdefault("svg2ooxml.geometry.matrix", matrix)

__all__ = ["algorithms", "fractional", "paths", "transforms", "matrix"]
