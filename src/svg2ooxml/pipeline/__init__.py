"""Public pipeline API re-export."""

from svg2ooxml.core.pipeline import navigation as navigation
from svg2ooxml.core.pipeline.navigation import (
    BookmarkTarget,
    CustomShowTarget,
    NavigationAction,
    NavigationKind,
    NavigationSpec,
    SlideTarget,
    parse_svg_navigation,
)
from svg2ooxml.core.pipeline.pipeline import DEFAULT_STAGE_NAMES, ConversionPipeline

__all__ = [
    "ConversionPipeline",
    "DEFAULT_STAGE_NAMES",
    "NavigationAction",
    "NavigationKind",
    "NavigationSpec",
    "SlideTarget",
    "BookmarkTarget",
    "CustomShowTarget",
    "parse_svg_navigation",
    "navigation",
]
