"""Recursive child conversion for resvg-backed group nodes."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.core.ir.shape_converters_resvg_context import GlobalTransformProxy
from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.ir.scene import ClipRef, Group, MaskInstance, MaskRef


class ResvgChildConversionMixin:
    def _resvg_node_source_element(self, node: Any) -> etree._Element | None:
        return self._resvg_canonical_source_element(getattr(node, "source", None))

    def _resvg_style_for_node(
        self,
        node: Any,
        fallback_style: StyleResult,
        *,
        element: etree._Element,
        element_local: str,
        use_paint_dict,
    ) -> StyleResult:
        node_source = self._resvg_node_source_element(node)
        if node_source is not None:
            paint_dict = self._style_resolver.compute_paint_style(
                node_source,
                context=self._css_context,
            )
            node_style = self._materialize_style(node_source, paint_dict)
            node_style = self._style_with_local_opacity(node_source, node_style)
            if element_local == "use":
                node_style = self._merge_use_styles(
                    fallback_style,
                    node_style,
                    use_element=element,
                    source_element=node_source,
                    use_paint_style=use_paint_dict,
                    multiply_opacity=False,
                )
        else:
            node_style = replace(fallback_style, opacity=1.0)
        return self._apply_resvg_paint_overrides(
            node,
            node_style,
            fallback_element=element,
            preserve_base_paint_opacity=node_source is not None,
            preserve_base_paint_presence=element_local == "use",
        )

    def _resvg_metadata_for_node(
        self,
        node: Any,
        node_style: StyleResult,
    ) -> dict[str, Any]:
        node_metadata = dict(node_style.metadata)
        self._attach_policy_metadata(node_metadata, "geometry")
        node_source = self._resvg_node_source_element(node)
        if node_source is not None:
            self._append_metadata_element_id(node_metadata, node_source.get("id"))
        use_instance = getattr(node, "use_source", None)
        if isinstance(use_instance, etree._Element):
            self._append_metadata_element_id(node_metadata, use_instance.get("id"))
        return node_metadata

    def _resvg_clip_mask_for_source(
        self,
        child_element: etree._Element | None,
    ) -> tuple[ClipRef | None, MaskRef | None, MaskInstance | None]:
        if child_element is None:
            return None, None, None
        child_clip_ref = self._resolve_clip_ref(child_element)
        child_mask_ref, child_mask_instance = self._resolve_mask_ref(child_element)
        return child_clip_ref, child_mask_ref, child_mask_instance

    def _resvg_child_global_transform(
        self,
        child: Any,
        *,
        parent_global: Any,
        node_transform_lookup: dict[int, Any],
        use_global_override: Matrix2D | None,
        original_global_transform: Any,
    ) -> Any:
        looked_up = node_transform_lookup.get(id(child))
        if looked_up is None:
            # Clone nodes from <use> expansion carry local transforms in the adapter.
            return parent_global

        child_global = self._matrix2d_from_resvg(looked_up)
        if use_global_override is None or original_global_transform is None:
            return child_global

        try:
            relative = (
                self._matrix2d_from_resvg(original_global_transform)
                .inverse()
                .multiply(child_global)
            )
            return use_global_override.multiply(relative)
        except Exception:
            return child_global

    def _convert_resvg_children(
        self,
        nodes,
        *,
        element: etree._Element,
        element_local: str,
        parent_style: StyleResult,
        parent_global: Any,
        use_paint_dict,
        use_global_override: Matrix2D | None,
        original_global_transform: Any,
    ) -> list[Any]:
        """Recursively convert resvg child nodes, flattening nested groups."""
        result_shapes: list[Any] = []
        node_transform_lookup = getattr(self, "_resvg_node_transform_lookup", {})
        for child in nodes:
            child_global = self._resvg_child_global_transform(
                child,
                parent_global=parent_global,
                node_transform_lookup=node_transform_lookup,
                use_global_override=use_global_override,
                original_global_transform=original_global_transform,
            )
            child_proxy = GlobalTransformProxy(child, child_global)
            child_style = self._resvg_style_for_node(
                child,
                parent_style,
                element=element,
                element_local=element_local,
                use_paint_dict=use_paint_dict,
            )
            child_metadata = self._resvg_metadata_for_node(child, child_style)
            child_source_element = self._resvg_node_source_element(child)
            child_element = (
                child_source_element if child_source_element is not None else element
            )
            child_clip_ref, child_mask_ref, child_mask_instance = (
                self._resvg_clip_mask_for_source(child_source_element)
            )
            child_node_type = type(child).__name__

            if child_node_type in ("GenericNode", "GroupNode"):
                nested = getattr(child, "children", []) or []
                if nested:
                    nested_shapes = self._convert_resvg_children(
                        nested,
                        element=element,
                        element_local=element_local,
                        parent_style=child_style,
                        parent_global=child_global,
                        use_paint_dict=use_paint_dict,
                        use_global_override=use_global_override,
                        original_global_transform=original_global_transform,
                    )
                    if nested_shapes:
                        result_shapes.append(
                            Group(
                                children=nested_shapes,
                                clip=child_clip_ref,
                                mask=child_mask_ref,
                                mask_instance=child_mask_instance,
                                opacity=(
                                    child_style.opacity
                                    if child_style.opacity != 1.0
                                    else 1.0
                                ),
                                metadata=child_metadata,
                            )
                        )
                continue

            primitive_shape = self._resvg_fast_primitive_shape(
                node_type=child_node_type,
                element=child_element,
                proxy_node=child_proxy,
                style=child_style,
                metadata=child_metadata,
                clip_ref=child_clip_ref,
                mask_ref=child_mask_ref,
                mask_instance=child_mask_instance,
            )
            if primitive_shape is not None:
                result_shapes.append(primitive_shape)
                continue

            child_shape = self._resvg_adapted_shape(
                node_type=child_node_type,
                proxy_node=child_proxy,
                element=child_element,
                style=child_style,
                metadata=child_metadata,
                clip_ref=child_clip_ref,
                mask_ref=child_mask_ref,
                mask_instance=child_mask_instance,
                child=True,
            )
            if isinstance(child_shape, list):
                result_shapes.extend(child_shape)
            elif child_shape is not None:
                result_shapes.append(child_shape)
        return result_shapes


__all__ = ["ResvgChildConversionMixin"]
