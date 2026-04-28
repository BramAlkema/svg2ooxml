"""Element rendering helpers for the DrawingML writer."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from svg2ooxml.ir.scene import Group, Image
from svg2ooxml.ir.shapes import Rectangle
from svg2ooxml.ir.text import TextFrame

from .clipmask import clip_bounds_for
from .group_runtime import (
    apply_group_wrapper_semantics,
    can_remove_group_wrapper,
    children_overlap,
    element_ids_for,
    group_xfrm_xml,
    metadata_has_bookmark_navigation,
    should_flatten_group_for_native_animation,
    translate_group_child_to_local_coordinates,
)
from .mask_alpha import apply_mask_alpha as _apply_mask_alpha
from .writer_base import logger


class DrawingMLElementMixin:
    """Render individual IR elements into DrawingML fragments."""

    def _render_elements(self, elements: Iterable, next_id: int) -> tuple[list[str], int]:
        fragments: list[str] = []
        current_id = next_id
        for element in elements:
            rendered = self._render_element(element, current_id)
            if rendered is None:
                continue
            fragments.extend(rendered[0])
            current_id = rendered[1]
        return fragments, current_id

    def _should_suppress_w3c_test_frame(self, element: object) -> bool:
        if not isinstance(element, Rectangle):
            return False
        scene_metadata = self._scene_metadata
        if not isinstance(scene_metadata, dict):
            return False
        source_path = scene_metadata.get("source_path")
        if not isinstance(source_path, str) or not source_path:
            return False
        normalized = source_path.replace("\\", "/")
        if not (normalized.startswith("tests/svg/") or "/tests/svg/" in normalized):
            return False
        return "test-frame" in element_ids_for(element)

    @staticmethod
    def _policy_for(metadata: dict[str, object] | None, target: str) -> dict[str, object]:
        if not metadata:
            return {}
        policy = metadata.get("policy")
        if not isinstance(policy, dict):
            return {}
        target_meta = policy.get(target)
        if isinstance(target_meta, dict):
            return target_meta
        return {}

    def _trace_writer(
        self,
        action: str,
        *,
        metadata: dict[str, object] | None = None,
        subject: str | None = None,
        stage: str = "writer",
    ) -> None:
        tracer = self._tracer
        if tracer is None:
            return
        tracer.record_stage_event(stage=stage, action=action, metadata=metadata, subject=subject)

    def _register_media(self, image: Image) -> str:
        return self._asset_pipeline.register_media(image)

    def register_filter_assets(self, metadata: dict[str, object] | None) -> None:
        self._asset_pipeline.register_filter_assets(metadata)

    def _render_group_filter_fallback(
        self,
        group: Group,
        shape_id: int,
        metadata: dict[str, object],
    ) -> str | None:
        return self._asset_pipeline.render_group_filter_fallback(group, shape_id, metadata)

    def _render_element(self, element, shape_id: int) -> tuple[list[str], int] | None:
        if self._should_suppress_w3c_test_frame(element):
            self._trace_writer(
                "shape_suppressed",
                stage="writer",
                metadata={"shape_id": shape_id, "reason": "w3c_test_frame"},
            )
            return None

        element, metadata = self._prepare_element_metadata(element)
        self._animation_pipeline.register_mapping(metadata, shape_id)
        element = self._apply_clip_mask_metadata(element, shape_id, metadata)
        hyperlink_xml = ""
        if isinstance(metadata, dict) and not isinstance(element, Group):
            hyperlink_xml = self._navigation.from_metadata(metadata, scope="shape") or ""

        if isinstance(element, TextFrame):
            return self._render_text_frame(element, shape_id, hyperlink_xml)
        if isinstance(element, Group):
            return self._render_group(element, shape_id, metadata, hyperlink_xml)
        return self._render_shape(element, shape_id, metadata, hyperlink_xml)

    def _prepare_element_metadata(self, element) -> tuple[object, dict[str, object]]:
        source_metadata = getattr(element, "metadata", None)
        if not isinstance(source_metadata, dict):
            return element, {}
        metadata = dict(source_metadata)
        mask_metadata = metadata.get("mask")
        if isinstance(mask_metadata, dict):
            metadata["mask"] = dict(mask_metadata)
        try:
            element = replace(element, metadata=metadata)
        except TypeError:
            pass
        self.register_filter_assets(metadata)
        return element, metadata

    def _apply_clip_mask_metadata(
        self,
        element,
        shape_id: int,
        metadata: dict[str, object],
    ):
        clip_bounds, clip_diags = clip_bounds_for(getattr(element, "clip", None))
        mask_xml, mask_diags = self._mask_pipeline.render(element)

        if clip_bounds is not None and isinstance(metadata, dict):
            metadata["_clip_bounds"] = clip_bounds

        if mask_xml == "<!-- HIDDEN -->" and hasattr(element, "opacity"):
            try:
                element = replace(element, opacity=0.0)
            except TypeError:
                pass

        mask_alpha = metadata.pop("_mask_alpha", None) if isinstance(metadata, dict) else None
        if mask_alpha is not None and 0.0 < mask_alpha < 1.0:
            element = _apply_mask_alpha(element, mask_alpha)
            self._trace_writer(
                "mask_alpha_shortcut",
                stage="mask",
                metadata={
                    "shape_id": shape_id,
                    "alpha": mask_alpha,
                    "element_type": type(element).__name__,
                },
            )

        for message in clip_diags:
            self._assets.add_diagnostic(message)
        for message in mask_diags:
            self._assets.add_diagnostic(message)
            logger.warning(message)
        return element

    def _render_text_frame(
        self,
        element: TextFrame,
        shape_id: int,
        hyperlink_xml: str,
    ) -> tuple[list[str], int]:
        if self._text_renderer is None:
            raise RuntimeError("Text renderer not initialised for current rendering run.")
        fragment, next_id = self._text_renderer.render(
            element,
            shape_id,
            hyperlink_xml=hyperlink_xml,
        )
        return [fragment], next_id

    def _render_group(
        self,
        element: Group,
        shape_id: int,
        metadata: dict[str, object],
        hyperlink_xml: str,
    ) -> tuple[list[str], int] | None:
        if hyperlink_xml:
            self._assets.add_diagnostic("Group-level navigation is not yet supported; hyperlink ignored.")
            logger.warning("Navigation on group elements is not supported; skipping hyperlink metadata.")

        fallback = self._render_group_filter_fallback(element, shape_id, metadata)
        if fallback is not None:
            self._trace_writer(
                "group_filter_fallback_rendered",
                stage="filter",
                metadata={"shape_id": shape_id},
            )
            return [fallback], shape_id + 1

        raster_fragment = self._try_render_raster_group(element, shape_id, metadata)
        if raster_fragment is not None:
            return [raster_fragment], shape_id + 1

        if should_flatten_group_for_native_animation(
            element,
            self._animation_pipeline.metadata_targets_animation,
        ):
            self._trace_writer(
                "group_flattened",
                stage="writer",
                metadata={"shape_id": shape_id, "reason": "native_animation_target"},
            )
            fragments, next_id = self._render_elements(element.children, shape_id)
            if not fragments:
                return None
            return fragments, next_id

        if self._can_flatten_leaf_group(element, metadata):
            children = element.children
            if (
                not can_remove_group_wrapper(element)
                or metadata_has_bookmark_navigation(metadata)
                or metadata.get("navigation") is not None
            ):
                children = apply_group_wrapper_semantics(element, metadata)
            fragments, next_id = self._render_elements(children, shape_id)
            if not fragments:
                return None
            return fragments, next_id

        return self._render_group_shape(element, shape_id)

    def _try_render_raster_group(
        self,
        element: Group,
        shape_id: int,
        metadata: dict[str, object],
    ) -> str | None:
        if (
            element.opacity >= 1.0
            or self._rasterizer is None
            or not children_overlap(element.children)
        ):
            return None
        raster = self._rasterizer.rasterize(element)
        if raster is None:
            return None
        fragment = self._emit_raster_group(raster, element, shape_id, metadata)
        if fragment is not None:
            self._trace_writer(
                "group_rasterized",
                stage="paint",
                metadata={
                    "shape_id": shape_id,
                    "reason": "overlapping_children_with_opacity",
                    "opacity": element.opacity,
                    "child_count": len(element.children),
                },
            )
        return fragment

    def _can_flatten_leaf_group(self, element: Group, metadata: dict[str, object]) -> bool:
        has_nested_groups = any(isinstance(child, Group) for child in element.children)
        return not has_nested_groups and not self._animation_pipeline.metadata_targets_animation(
            element.metadata
        )

    def _render_group_shape(self, element: Group, shape_id: int) -> tuple[list[str], int] | None:
        group_bbox = element.bbox
        local_children = [
            translate_group_child_to_local_coordinates(
                child,
                group_bbox.x,
                group_bbox.y,
            )
            for child in element.children
        ]
        child_fragments, next_id = self._render_elements(local_children, shape_id + 1)
        if not child_fragments:
            return None

        children_xml = "\n".join(child_fragments)
        group_xml = (
            f"<p:grpSp>"
            f"<p:nvGrpSpPr>"
            f'<p:cNvPr id="{shape_id}" name="Group {shape_id}"/>'
            f"<p:cNvGrpSpPr/>"
            f"<p:nvPr/>"
            f"</p:nvGrpSpPr>"
            f"<p:grpSpPr>"
            f"{group_xfrm_xml(element)}"
            f"</p:grpSpPr>"
            f"{children_xml}"
            f"</p:grpSp>"
        )
        return [group_xml], next_id

    def _render_shape(
        self,
        element,
        shape_id: int,
        metadata: dict[str, object],
        hyperlink_xml: str,
    ) -> tuple[list[str], int] | None:
        if self._shape_renderer is None:
            raise RuntimeError("Shape renderer not initialised for current rendering run.")
        rendered = self._shape_renderer.render(
            element,
            shape_id,
            metadata,
            hyperlink_xml=hyperlink_xml,
        )
        if rendered is not None:
            fragment, next_id = rendered
            return [fragment], next_id

        logger.debug("Skipping unsupported IR element type: %s", type(element).__name__)
        return None

    def _emit_raster_group(self, raster, group, shape_id, metadata) -> str | None:
        return self._asset_pipeline.emit_raster_group(raster, group, shape_id, metadata)

    def _build_animation_xml(self) -> str:
        return self._animation_pipeline.build(max_shape_id=getattr(self, "_max_shape_id", 0))


__all__ = ["DrawingMLElementMixin"]
