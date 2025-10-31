"""Modern map package exposing converter, mapper, and tracer shims."""

from __future__ import annotations

from importlib import import_module
import sys

converter = import_module("svg2ooxml.map.converter")
mapper = import_module("svg2ooxml.map.mapper")
tracer = import_module("svg2ooxml.map.tracer")

sys.modules.setdefault("svg2ooxml.map.converter", converter)
sys.modules.setdefault("svg2ooxml.map.mapper", mapper)
sys.modules.setdefault("svg2ooxml.map.tracer", tracer)

__all__ = ["converter", "mapper", "tracer"]
