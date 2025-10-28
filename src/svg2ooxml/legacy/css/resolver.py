"""Compatibility wrapper for the migrated style resolver."""

from __future__ import annotations

from svg2ooxml.common.style.resolver import *  # noqa: F401,F403

__all__ = [
    "CSSDeclaration",
    "CSSRule",
    "CompiledSelector",
    "SelectorPart",
    "StyleContext",
    "StyleResolver",
]
