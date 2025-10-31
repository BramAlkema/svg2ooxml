"""Converter compatibility layer backed by core traversal modules."""

from __future__ import annotations

from importlib import import_module
import sys
from typing import Any

_ATTR_EXPORTS = {
    "GeometryPayload": "svg2ooxml.core.traversal.clipping",
    "extract_url_id": "svg2ooxml.core.traversal.clipping",
    "resolve_clip_ref": "svg2ooxml.core.traversal.clipping",
    "generate_clip_geometry": "svg2ooxml.core.traversal.clipping",
    "resolve_mask_ref": "svg2ooxml.core.traversal.clipping",
    "DEFAULT_TOLERANCE": "svg2ooxml.core.traversal.constants",
    "CoordinateSpace": "svg2ooxml.core.traversal.coordinate_space",
    "IRScene": "svg2ooxml.core.ir.converter",
    "IRConverter": "svg2ooxml.core.ir.converter",
    "EMFPathAdapter": "svg2ooxml.drawingml.bridges.emf_path_adapter",
    "EMFPathResult": "svg2ooxml.drawingml.bridges.emf_path_adapter",
    "PathStyle": "svg2ooxml.drawingml.bridges.emf_path_adapter",
    "render_emf_fallback": "svg2ooxml.core.ir.fallbacks",
    "render_bitmap_fallback": "svg2ooxml.core.ir.fallbacks",
    "transform_axis_aligned_rect": "svg2ooxml.core.traversal.geometry_utils",
    "is_axis_aligned": "svg2ooxml.core.traversal.geometry_utils",
    "scaled_corner_radius": "svg2ooxml.core.traversal.geometry_utils",
    "HyperlinkProcessor": "svg2ooxml.core.hyperlinks.processor",
    "apply_marker_metadata": "svg2ooxml.core.traversal.marker_runtime",
    "build_marker_shapes": "svg2ooxml.core.traversal.marker_runtime",
    "MarkerInstance": "svg2ooxml.core.traversal.markers",
    "MarkerDefinition": "svg2ooxml.core.traversal.markers",
    "build_marker_transform": "svg2ooxml.core.traversal.markers",
    "apply_local_transform": "svg2ooxml.core.traversal.markers",
    "parse_marker_definition": "svg2ooxml.core.traversal.markers",
    "MarkerTransform": "svg2ooxml.core.traversal.markers",
    "MaskProcessor": "svg2ooxml.core.masks",
    "MaskProcessingResult": "svg2ooxml.core.masks",
    "PolicyHooksMixin": "svg2ooxml.core.ir.policy_hooks",
    "convert_rect": "svg2ooxml.core.ir.rectangles",
    "collect_resvg_clip_definitions": "svg2ooxml.core.traversal.bridges.resvg_clip_mask",
    "collect_resvg_mask_info": "svg2ooxml.core.traversal.bridges.resvg_clip_mask",
    "GradientStopDescriptor": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "describe_gradient_element": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "RadialGradientDescriptor": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "LinearGradientDescriptor": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "PatternDescriptor": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "describe_radial_gradient": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "build_mesh_gradient_element": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "describe_pattern_element": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "build_linear_gradient_element": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "build_pattern_element": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "describe_pattern": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "MeshGradientDescriptor": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "build_radial_gradient_element": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "GradientDescriptor": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "describe_linear_gradient": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "ShapeConversionMixin": "svg2ooxml.core.ir.shape_converters",
    "SmartFontBridge": "svg2ooxml.core.ir.smart_font_bridge",
    "StyleExtractor": "svg2ooxml.core.styling.style_extractor",
    "StyleResult": "svg2ooxml.core.styling.style_extractor",
    "extract_style": "svg2ooxml.core.styling.style_runtime",
    "FONT_FALLBACKS": "svg2ooxml.core.ir.text_converter",
    "TextConverter": "svg2ooxml.core.ir.text_converter",
    "TextConversionPipeline": "svg2ooxml.core.ir.text_pipeline",
    "TransformParser": "svg2ooxml.core.traversal.transform_parser",
    "TraverseCallback": "svg2ooxml.core.traversal.traversal",
    "ElementTraversal": "svg2ooxml.core.traversal.traversal",
    "TraversalHooksMixin": "svg2ooxml.core.traversal.hooks",
    "process_group": "svg2ooxml.core.traversal.runtime",
    "resolve_active_navigation": "svg2ooxml.core.traversal.runtime",
    "process_generic": "svg2ooxml.core.traversal.runtime",
    "process_anchor": "svg2ooxml.core.traversal.runtime",
    "push_element_transform": "svg2ooxml.core.traversal.runtime",
    "process_use": "svg2ooxml.core.traversal.runtime",
    "local_name": "svg2ooxml.core.traversal.runtime",
    "wrap_symbol_clone": "svg2ooxml.core.styling.use_expander",
    "propagate_symbol_use_attributes": "svg2ooxml.core.styling.use_expander",
    "compute_use_transform": "svg2ooxml.core.styling.use_expander",
    "apply_use_attributes": "svg2ooxml.core.styling.use_expander",
    "resolve_use_offsets": "svg2ooxml.core.styling.use_expander",
    "apply_use_transform": "svg2ooxml.core.styling.use_expander",
    "instantiate_use_target": "svg2ooxml.core.styling.use_expander",
}

_MODULE_ALIASES = {
    "clipping": "svg2ooxml.core.traversal.clipping",
    "constants": "svg2ooxml.core.traversal.constants",
    "coordinate_space": "svg2ooxml.core.traversal.coordinate_space",
    "core": "svg2ooxml.core.ir.converter",
    "emf_adapter": "svg2ooxml.drawingml.bridges.emf_path_adapter",
    "fallbacks": "svg2ooxml.core.ir.fallbacks",
    "geometry_utils": "svg2ooxml.core.traversal.geometry_utils",
    "hyperlinks": "svg2ooxml.core.hyperlinks.processor",
    "marker_runtime": "svg2ooxml.core.traversal.marker_runtime",
    "markers": "svg2ooxml.core.traversal.markers",
    "mask_processor": "svg2ooxml.core.masks",
    "policy_hooks": "svg2ooxml.core.ir.policy_hooks",
    "rectangles": "svg2ooxml.core.ir.rectangles",
    "resvg_clip_mask": "svg2ooxml.core.traversal.bridges.resvg_clip_mask",
    "resvg_paint_bridge": "svg2ooxml.drawingml.bridges.resvg_paint_bridge",
    "shape_converters": "svg2ooxml.core.ir.shape_converters",
    "smart_font_bridge": "svg2ooxml.core.ir.smart_font_bridge",
    "styles": "svg2ooxml.core.styling.style_extractor",
    "styles_runtime": "svg2ooxml.core.styling.style_runtime",
    "text": "svg2ooxml.core.ir.text_converter",
    "text_pipeline": "svg2ooxml.core.ir.text_pipeline",
    "transform_parser": "svg2ooxml.core.traversal.transform_parser",
    "traversal": "svg2ooxml.core.traversal.traversal",
    "traversal_hooks": "svg2ooxml.core.traversal.hooks",
    "traversal_runtime": "svg2ooxml.core.traversal.runtime",
    "use_runtime": "svg2ooxml.core.styling.use_expander",
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
