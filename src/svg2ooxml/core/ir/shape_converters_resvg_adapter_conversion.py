"""Adapter dispatch for resvg-backed shape conversion."""

from __future__ import annotations

from typing import Any

from lxml import etree

from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.ir.scene import ClipRef, MaskInstance, MaskRef

_ADAPTER_METHODS = {
    "PathNode": "from_path_node",
    "RectNode": "from_rect_node",
    "CircleNode": "from_circle_node",
    "EllipseNode": "from_ellipse_node",
    "LineNode": "from_line_node",
    "PolyNode": "from_poly_node",
}


class ResvgAdapterConversionMixin:
    def _resvg_fast_primitive_shape(
        self,
        *,
        node_type: str,
        element: etree._Element,
        proxy_node: Any,
        style: StyleResult,
        metadata: dict[str, Any],
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
        trace: bool = False,
    ) -> Any | None:
        if node_type == "RectNode":
            shape = self._resvg_rect_to_rectangle(
                element=element,
                resvg_node=proxy_node,
                style=style,
                metadata=metadata,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
            )
        elif node_type == "CircleNode":
            shape = self._resvg_circle_to_circle(
                element=element,
                resvg_node=proxy_node,
                style=style,
                metadata=metadata,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
            )
        elif node_type == "EllipseNode":
            shape = self._resvg_ellipse_to_ellipse(
                element=element,
                resvg_node=proxy_node,
                style=style,
                metadata=metadata,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
            )
        else:
            return None

        if shape is not None and trace:
            self._trace_geometry_decision(element, "resvg", shape.metadata)
        return shape

    def _resvg_adapter_segments(
        self,
        *,
        node_type: str,
        proxy_node: Any,
        element: etree._Element,
        child: bool = False,
    ) -> Any | None:
        method_name = _ADAPTER_METHODS.get(node_type)
        if method_name is None:
            return None

        from svg2ooxml.drawingml.bridges.resvg_shape_adapter import ResvgShapeAdapter

        adapter = ResvgShapeAdapter()
        try:
            return getattr(adapter, method_name)(proxy_node)
        except Exception as exc:
            if child:
                self._logger.debug(
                    "Resvg adapter failed for %s child: %s",
                    element.get("id") or f"<{node_type}>",
                    exc,
                )
            else:
                self._logger.debug(
                    "Resvg adapter failed for %s: %s",
                    element.get("id") or f"<{node_type}>",
                    exc,
                )
            return None

    def _resvg_adapted_shape(
        self,
        *,
        node_type: str,
        proxy_node: Any,
        element: etree._Element,
        style: StyleResult,
        metadata: dict[str, Any],
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
        child: bool = False,
    ) -> Any | None:
        segments = self._resvg_adapter_segments(
            node_type=node_type,
            proxy_node=proxy_node,
            element=element,
            child=child,
        )
        if not segments:
            return None

        return self._resvg_segments_to_path(
            element=element,
            segments=segments,
            coord_space=CoordinateSpace(),
            style=style,
            metadata=metadata,
            clip_ref=clip_ref,
            mask_ref=mask_ref,
            mask_instance=mask_instance,
        )


__all__ = ["ResvgAdapterConversionMixin"]
