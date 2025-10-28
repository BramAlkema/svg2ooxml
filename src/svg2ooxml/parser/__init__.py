"""Public parser API backed by the modern core implementation."""

from __future__ import annotations

import sys
from importlib import import_module
from typing import Any

from svg2ooxml.core import parser as _core_parser

from svg2ooxml.core.parser import *  # noqa: F401,F403

__all__ = list(getattr(_core_parser, "__all__", ()))

_SUBMODULE_REDIRECTS = {
    "svg_parser": "svg2ooxml.core.parser.svg_parser",
    "content_cleaner": "svg2ooxml.core.parser.content_cleaner",
    "dom_loader": "svg2ooxml.core.parser.dom_loader",
    "colors": "svg2ooxml.core.parser.colors",
    "normalization": "svg2ooxml.core.parser.normalization",
    "reference_collector": "svg2ooxml.core.parser.reference_collector",
    "references": "svg2ooxml.core.parser.references",
    "statistics": "svg2ooxml.core.parser.statistics",
    "style_context": "svg2ooxml.core.parser.style_context",
    "units": "svg2ooxml.core.parser.units",
    "validators": "svg2ooxml.core.parser.validators",
    "preprocess": "svg2ooxml.core.parser.preprocess",
    "geometry": "svg2ooxml.common.geometry",
    "result": "svg2ooxml.core.parser.result",
    "switch_evaluator": "svg2ooxml.core.parser.switch_evaluator",
}

_CORE_SUBPACKAGES = {
    "batch": "svg2ooxml.core.parser.batch",
}

for _alias, _module_path in _SUBMODULE_REDIRECTS.items():
    _module = import_module(_module_path)
    sys.modules[f"{__name__}.{_alias}"] = _module
    setattr(sys.modules[__name__], _alias, _module)

for _alias, _module_path in _CORE_SUBPACKAGES.items():
    _module = import_module(_module_path)
    sys.modules[f"{__name__}.{_alias}"] = _module
    setattr(sys.modules[__name__], _alias, _module)


def __getattr__(name: str) -> Any:
    if name in _SUBMODULE_REDIRECTS or name in _CORE_SUBPACKAGES:
        return getattr(sys.modules[__name__], name)
    raise AttributeError(f"module {__name__} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(
        set(globals().keys())
        | set(__all__)
        | set(_SUBMODULE_REDIRECTS)
        | set(_CORE_SUBPACKAGES)
    )
