"""Mapper compatibility surface backed by the core pipeline."""

from __future__ import annotations

from importlib import import_module
import sys
from typing import Any

_ATTR_EXPORTS = {
    "ClipComputeResult": "svg2ooxml.core.traversal.clip_geometry",
    "ClipCustGeom": "svg2ooxml.core.traversal.clip_geometry",
    "ClipFallback": "svg2ooxml.core.traversal.clip_geometry",
    "ClipMediaMeta": "svg2ooxml.core.traversal.clip_geometry",
    "ClipPathSegment": "svg2ooxml.core.traversal.clip_geometry",
    "compute_clip_geometry": "svg2ooxml.core.traversal.clip_geometry",
    "clip_result_to_xml": "svg2ooxml.core.pipeline.mappers.clip_render",
    "GroupMapper": "svg2ooxml.core.pipeline.mappers.group_mapper",
    "ImageProcessingAdapter": "svg2ooxml.core.pipeline.mappers.image_adapter",
    "ImageProcessingResult": "svg2ooxml.core.pipeline.mappers.image_adapter",
    "create_image_adapter": "svg2ooxml.core.pipeline.mappers.image_adapter",
    "ImageDecision": "svg2ooxml.core.pipeline.mappers.image_mapper",
    "ImageMapper": "svg2ooxml.core.pipeline.mappers.image_mapper",
    "Mapper": "svg2ooxml.core.pipeline.mappers.base",
    "MapperError": "svg2ooxml.core.pipeline.mappers.base",
    "MapperResult": "svg2ooxml.core.pipeline.mappers.base",
    "OutputFormat": "svg2ooxml.core.pipeline.mappers.base",
    "validate_mapper_result": "svg2ooxml.core.pipeline.mappers.base",
    "PathDecision": "svg2ooxml.core.pipeline.mappers.path_mapper",
    "PathMapper": "svg2ooxml.core.pipeline.mappers.path_mapper",
    "TextMapper": "svg2ooxml.core.pipeline.mappers.text_mapper",
}

_MODULE_ALIASES = {
    "clip_geometry": "svg2ooxml.core.traversal.clip_geometry",
    "clip_render": "svg2ooxml.core.pipeline.mappers.clip_render",
    "group_mapper": "svg2ooxml.core.pipeline.mappers.group_mapper",
    "image_adapter": "svg2ooxml.core.pipeline.mappers.image_adapter",
    "image_mapper": "svg2ooxml.core.pipeline.mappers.image_mapper",
    "path_mapper": "svg2ooxml.core.pipeline.mappers.path_mapper",
    "text_mapper": "svg2ooxml.core.pipeline.mappers.text_mapper",
    "base": "svg2ooxml.core.pipeline.mappers.base",
}

__all__ = sorted(set(_ATTR_EXPORTS) | set(_MODULE_ALIASES))


def __getattr__(name: str) -> Any:
    if name in _ATTR_EXPORTS:
        module = import_module(_ATTR_EXPORTS[name])
        return getattr(module, name)
    if name in _MODULE_ALIASES:
        target = _MODULE_ALIASES[name]
        module = import_module(target)
        alias = f"{__name__}.{name}"
        if alias not in sys.modules:
            sys.modules[alias] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)


for module_name, target in _MODULE_ALIASES.items():
    alias = f"{__name__}.{module_name}"
    if alias not in sys.modules:
        sys.modules[alias] = import_module(target)
