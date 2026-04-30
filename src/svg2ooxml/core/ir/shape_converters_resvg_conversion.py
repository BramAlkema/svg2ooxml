"""Main resvg-backed shape conversion traversal."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.core.ir.shape_converters_resvg_adapter_conversion import (
    ResvgAdapterConversionMixin,
)
from svg2ooxml.core.ir.shape_converters_resvg_children import (
    ResvgChildConversionMixin,
)
from svg2ooxml.core.ir.shape_converters_resvg_context import (
    GlobalTransformProxy,
    ResvgConversionContextMixin,
)
from svg2ooxml.core.ir.shape_converters_resvg_paint_overrides import (
    ResvgPaintOverrideMixin,
)
from svg2ooxml.core.styling.stroke_width_policy import (
    apply_transform_stroke_width_policy,
)
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.ir.scene import Group


class ResvgConversionMixin(
    ResvgConversionContextMixin,
    ResvgPaintOverrideMixin,
    ResvgAdapterConversionMixin,
    ResvgChildConversionMixin,
):
    def _convert_via_resvg(self, element: etree._Element, coord_space: CoordinateSpace):
        """Convert element using resvg adapters."""
        context = self._resvg_prepare_context(element, coord_space)
        if context is None:
            return None

        node_type = type(context.resvg_node).__name__
        proxy_node = GlobalTransformProxy(
            context.resvg_node,
            context.global_transform,
        )
        shape_style = (
            apply_transform_stroke_width_policy(
                context.style,
                element=element,
                matrix=context.global_transform,
                metadata=context.metadata,
            )
            if node_type in ("RectNode", "CircleNode", "EllipseNode")
            else context.style
        )

        primitive_shape = self._resvg_fast_primitive_shape(
            node_type=node_type,
            element=element,
            proxy_node=proxy_node,
            style=shape_style,
            metadata=context.metadata,
            clip_ref=context.clip_ref,
            mask_ref=context.mask_ref,
            mask_instance=context.mask_instance,
            trace=True,
        )
        if primitive_shape is not None:
            return primitive_shape

        if node_type in ("GenericNode", "GroupNode"):
            children = getattr(context.resvg_node, "children", []) or []
            if children:
                group_children = self._convert_resvg_children(
                    children,
                    element=element,
                    element_local=context.element_local,
                    parent_style=context.style,
                    parent_global=context.global_transform,
                    use_paint_dict=context.use_paint_dict,
                    use_global_override=context.use_global_override,
                    original_global_transform=context.original_global_transform,
                )
                if group_children:
                    group = Group(
                        children=group_children,
                        clip=context.clip_ref,
                        mask=context.mask_ref,
                        mask_instance=context.mask_instance,
                        opacity=context.style.opacity,
                        metadata=context.metadata,
                    )
                    self._trace_geometry_decision(element, "resvg", group.metadata)
                    return group

        shape_style = apply_transform_stroke_width_policy(
            context.style,
            element=element,
            matrix=context.global_transform,
            metadata=context.metadata,
        )
        return self._resvg_adapted_shape(
            node_type=node_type,
            proxy_node=proxy_node,
            element=element,
            style=shape_style,
            metadata=context.metadata,
            clip_ref=context.clip_ref,
            mask_ref=context.mask_ref,
            mask_instance=context.mask_instance,
        )


__all__ = ["ResvgConversionMixin"]
