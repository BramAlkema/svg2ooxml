"""Context setup for resvg-backed shape conversion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.ir.scene import ClipRef, MaskInstance, MaskRef


class GlobalTransformProxy:
    """Proxy a resvg node while exposing a caller-supplied global transform."""

    def __init__(self, target: Any, global_transform: Any) -> None:
        self._target = target
        self.transform = global_transform

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)


@dataclass(slots=True)
class ResvgConversionContext:
    resvg_node: Any
    element_local: str
    style: StyleResult
    metadata: dict[str, Any]
    source_element: etree._Element | None
    use_paint_dict: Mapping[str, Any] | None
    global_transform: Any
    original_global_transform: Any
    use_global_override: Matrix2D | None
    clip_ref: ClipRef | None
    mask_ref: MaskRef | None
    mask_instance: MaskInstance | None


class ResvgConversionContextMixin:
    def _resvg_prepare_context(
        self,
        element: etree._Element,
        coord_space: CoordinateSpace,
    ) -> ResvgConversionContext | None:
        resvg_lookup = getattr(self, "_resvg_element_lookup", {})
        resvg_node = resvg_lookup.get(element)
        if resvg_node is None:
            return None

        global_transform = self._resvg_global_transform(element, resvg_node)
        element_local = self._resvg_element_local(element)
        style, metadata, use_paint_dict = self._resvg_base_style(
            element,
            element_local,
        )
        source_element = self._resvg_source_element(resvg_node)
        if isinstance(source_element, etree._Element):
            self._append_metadata_element_id(metadata, source_element.get("id"))
            if element_local == "use":
                paint_dict = self._style_resolver.compute_paint_style(
                    source_element,
                    context=self._css_context,
                )
                source_style = self._materialize_style(source_element, paint_dict)
                style = self._merge_use_styles(
                    style,
                    source_style,
                    use_element=element,
                    source_element=source_element,
                    use_paint_style=use_paint_dict,
                )
                metadata.update(source_style.metadata or {})

        original_global_transform = global_transform
        use_global_override: Matrix2D | None = None
        if element_local == "use" and isinstance(source_element, etree._Element):
            use_global_override = self._resvg_use_global_override(
                element,
                source_element,
                coord_space,
            )
            global_transform = use_global_override
        else:
            # Resvg's local tree currently omits nested <svg> viewport transforms.
            # The traversal CTM includes them, plus ordinary XML transforms.
            global_transform = coord_space.current

        style = self._apply_resvg_paint_overrides(
            resvg_node,
            style,
            fallback_element=element,
            preserve_base_paint_opacity=True,
            preserve_base_paint_presence=element_local == "use",
        )
        clip_ref, mask_ref, mask_instance = self._resvg_clip_mask_refs(
            element,
            element_local,
            source_element,
            global_transform,
        )

        return ResvgConversionContext(
            resvg_node=resvg_node,
            element_local=element_local,
            style=style,
            metadata=metadata,
            source_element=source_element,
            use_paint_dict=use_paint_dict,
            global_transform=global_transform,
            original_global_transform=original_global_transform,
            use_global_override=use_global_override,
            clip_ref=clip_ref,
            mask_ref=mask_ref,
            mask_instance=mask_instance,
        )

    def _resvg_global_transform(self, element: etree._Element, resvg_node: Any) -> Any:
        from svg2ooxml.core.ir.resvg_bridge import ResvgBridge

        sig = ResvgBridge._element_signature(element)
        global_transform_lookup = getattr(self, "_resvg_global_transform_lookup", {})
        global_transform = global_transform_lookup.get(sig)

        if global_transform is None:
            node_transform_lookup = getattr(self, "_resvg_node_transform_lookup", {})
            global_transform = node_transform_lookup.get(id(resvg_node))
            if global_transform is None:
                self._logger.warning("No global transform found for signature: %s", sig)
        return global_transform

    def _resvg_element_local(self, element: etree._Element) -> str:
        if hasattr(self, "_local_name"):
            return self._local_name(element.tag).lower()
        return element.tag.split("}")[-1].lower() if isinstance(element.tag, str) else ""

    def _resvg_base_style(
        self,
        element: etree._Element,
        element_local: str,
    ) -> tuple[StyleResult, dict[str, Any], Mapping[str, Any] | None]:
        # Keep runtime-style lookup patchable via the legacy module path.
        from svg2ooxml.core.ir import shape_converters as shape_converters_module

        style = shape_converters_module.styles_runtime.extract_style(self, element)
        use_paint_dict: Mapping[str, Any] | None = None
        if element_local == "use":
            try:
                use_paint_dict = (
                    self._style_extractor._compute_paint_style_with_inheritance(
                        element,
                        context=self._css_context,
                    )
                )
            except Exception:
                use_paint_dict = self._style_resolver.compute_paint_style(
                    element,
                    context=self._css_context,
                )
            style = self._materialize_style(element, dict(use_paint_dict))
        style = self._style_with_local_opacity(element, style)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")
        return style, metadata, use_paint_dict

    def _resvg_source_element(self, resvg_node: Any) -> etree._Element | None:
        use_source = getattr(resvg_node, "use_source", None)
        source_element = None
        if isinstance(use_source, etree._Element):
            href_attr = use_source.get(
                "{http://www.w3.org/1999/xlink}href"
            ) or use_source.get("href")
            reference_id = self._normalize_href_reference(href_attr)
            if reference_id:
                source_element = self._element_index.get(reference_id)
        if source_element is None:
            source_element = getattr(resvg_node, "source", None)
        return self._resvg_canonical_source_element(source_element)

    def _resvg_canonical_source_element(
        self,
        candidate: etree._Element | None,
    ) -> etree._Element | None:
        if not isinstance(candidate, etree._Element):
            return None
        source_id = candidate.get("data-svg2ooxml-source-id") or candidate.get("id")
        if isinstance(source_id, str) and source_id:
            indexed = self._element_index.get(source_id)
            if isinstance(indexed, etree._Element):
                return indexed
        return candidate

    def _resvg_use_global_override(
        self,
        element: etree._Element,
        source_element: etree._Element,
        coord_space: CoordinateSpace,
    ) -> Matrix2D:
        from svg2ooxml.core.styling.use_expander import compose_use_transform

        combined = compose_use_transform(
            self,
            element,
            source_element,
            tolerance=DEFAULT_TOLERANCE,
        )
        local_transform = self._matrix_from_transform(element.get("transform"))
        try:
            parent_transform = coord_space.current.multiply(local_transform.inverse())
        except Exception:
            parent_transform = coord_space.current
        return parent_transform.multiply(combined)

    def _resvg_clip_mask_refs(
        self,
        element: etree._Element,
        element_local: str,
        source_element: etree._Element | None,
        use_transform: Matrix2D | None,
    ) -> tuple[ClipRef | None, MaskRef | None, MaskInstance | None]:
        clip_ref = self._resolve_clip_ref(element, use_transform=use_transform)
        mask_ref, mask_instance = self._resolve_mask_ref(element)
        if element_local == "use" and isinstance(source_element, etree._Element):
            if clip_ref is None:
                clip_ref = self._resolve_clip_ref(
                    source_element,
                    use_transform=use_transform,
                )
            if mask_ref is None and mask_instance is None:
                mask_ref, mask_instance = self._resolve_mask_ref(source_element)
        return clip_ref, mask_ref, mask_instance


__all__ = [
    "GlobalTransformProxy",
    "ResvgConversionContext",
    "ResvgConversionContextMixin",
]
