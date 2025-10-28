"""svg2ooxml – SVG to Office Open XML conversion toolkit."""

from __future__ import annotations

from importlib import metadata

from .core.converter import ConvertResult, Converter
from .core.pipeline import ConversionPipeline, DEFAULT_STAGE_NAMES

try:
    __version__ = metadata.version("svg2ooxml")
except metadata.PackageNotFoundError:  # pragma: no cover - local editable installs
    __version__ = "0.0.dev0"

__all__ = [
    "Converter",
    "ConvertResult",
    "ConversionPipeline",
    "DEFAULT_STAGE_NAMES",
    "__version__",
]

