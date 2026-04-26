"""Shared model objects for CSS style resolution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

from svg2ooxml.common.style.selectors import CompiledSelector

if TYPE_CHECKING:
    from svg2ooxml.core.parser.units import ConversionContext

PropertyHandler = Callable[[str], object]


class CSSOrigin(IntEnum):
    """CSS cascade origin levels per CSS Cascade 4 spec."""

    USER_AGENT = 1
    AUTHOR = 2
    PRESENTATION_ATTR = 3
    INLINE = 4


@dataclass(frozen=True)
class PropertyDescriptor:
    """Maps CSS property names to resolver keys and parsers."""

    key: str
    parser: PropertyHandler


@dataclass(frozen=True)
class StyleContext:
    """Viewport-aware context for CSS evaluation."""

    conversion: ConversionContext
    viewport_width: float
    viewport_height: float


@dataclass(frozen=True)
class CSSDeclaration:
    """Single CSS declaration."""

    name: str
    value: str
    important: bool
    origin: CSSOrigin = CSSOrigin.AUTHOR


@dataclass(frozen=True)
class CSSRule:
    """Qualified CSS rule with associated selectors."""

    selectors: tuple[CompiledSelector, ...]
    declarations: tuple[CSSDeclaration, ...]
    order: int
    origin: CSSOrigin = CSSOrigin.AUTHOR


__all__ = [
    "CSSDeclaration",
    "CSSOrigin",
    "CSSRule",
    "PropertyDescriptor",
    "PropertyHandler",
    "StyleContext",
]
