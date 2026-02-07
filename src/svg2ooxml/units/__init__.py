
"""Unit conversion helpers wrapped from ``svg2ooxml.common.units``."""

from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType

_COMMON_PREFIX = "svg2ooxml.common.units"


def _expose(name: str) -> ModuleType:
    module = import_module(f"{_COMMON_PREFIX}.{name}")
    sys.modules.setdefault(f"svg2ooxml.units.{name}", module)
    return module


conversion = import_module(f"{_COMMON_PREFIX}.conversion")
converters = _expose("converters")
scalars = import_module(f"{_COMMON_PREFIX}.scalars")

sys.modules.setdefault("svg2ooxml.units.conversion", conversion)
sys.modules.setdefault("svg2ooxml.units.scalars", scalars)

__all__ = [
    "conversion",
    "converters",
    "scalars",
    "ConversionContext",
    "DEFAULT_DPI",
    "EMU_PER_CM",
    "EMU_PER_INCH",
    "EMU_PER_MM",
    "EMU_PER_PICA",
    "EMU_PER_POINT",
    "EMU_PER_PX_AT_DEFAULT_DPI",
    "EMU_PER_Q",
    "PX_PER_INCH",
    "UnitConverter",
    "emu_to_px",
    "emu_to_unit",
    "px_to_emu",
]

ConversionContext = conversion.ConversionContext
DEFAULT_DPI = conversion.DEFAULT_DPI
EMU_PER_CM = conversion.EMU_PER_CM
EMU_PER_INCH = conversion.EMU_PER_INCH
EMU_PER_MM = conversion.EMU_PER_MM
EMU_PER_PICA = conversion.EMU_PER_PICA
EMU_PER_POINT = conversion.EMU_PER_POINT
EMU_PER_PX_AT_DEFAULT_DPI = conversion.EMU_PER_PX_AT_DEFAULT_DPI
EMU_PER_Q = conversion.EMU_PER_Q
PX_PER_INCH = scalars.PX_PER_INCH
UnitConverter = conversion.UnitConverter
emu_to_px = conversion.emu_to_px
emu_to_unit = conversion.emu_to_unit
px_to_emu = conversion.px_to_emu
