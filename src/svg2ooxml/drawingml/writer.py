"""DrawingML writer that renders IR scenes to slide XML fragments."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from svg2ooxml.core.ir import IRScene
from svg2ooxml.ir.scene import Group, Image, SceneGraph
from svg2ooxml.ir.shapes import Rectangle
from svg2ooxml.ir.text import TextFrame

from .animation_pipeline import AnimationPipeline
from .assets import AssetRegistry
from .clipmask import clip_bounds_for
from .generator import EMU_PER_PX, DrawingMLPathGenerator, px_to_emu
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
from .mask_pipeline import MaskPipeline
from .navigation_runtime import NavigationRegistrar
from .pipelines.asset_pipeline import AssetPipeline
from .rasterizer import SKIA_AVAILABLE, Rasterizer
from .result import DrawingMLRenderResult
from .shape_renderer import DrawingMLShapeRenderer
from .text_renderer import DrawingMLTextRenderer

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.tracing import ConversionTracer
    from svg2ooxml.services.image_service import ImageService

DEFAULT_SLIDE_SIZE = (9144000, 6858000)  # 10" x 7.5"

logger = logging.getLogger(__name__)


def _assets_root() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "pptx_scaffold"


class DrawingMLWriter:
    """Render IR scene graphs into DrawingML shape fragments."""

    def __init__(self, *, template_dir: Path | None = None, image_service: ImageService | None = None) -> None:
        self._template_dir = template_dir or _assets_root()
        self._image_service = image_service
        self._slide_template = (self._template_dir / "slide_template.xml").read_text(encoding="utf-8")
        self._text_template = (self._template_dir / "text_shape_template.xml").read_text(encoding="utf-8")
        self._rectangle_template = (self._template_dir / "shape_rectangle.xml").read_text(encoding="utf-8")
        self._preset_template = (self._template_dir / "shape_preset.xml").read_text(encoding="utf-8")
        self._path_template = (self._template_dir / "shape_path.xml").read_text(encoding="utf-8")
        self._line_template = (self._template_dir / "shape_line.xml").read_text(encoding="utf-8")
        self._picture_template = (self._template_dir / "picture_shape.xml").read_text(encoding="utf-8")
        self._wordart_template = (self._template_dir / "wordart_shape_template.xml").read_text(encoding="utf-8")
        self._path_generator = DrawingMLPathGenerator()
        self._asset_pipeline = AssetPipeline(image_service=image_service)
        self._asset_registry: AssetRegistry | None = None
        self._navigation = NavigationRegistrar()
        self._mask_pipeline = MaskPipeline()
        self._rasterizer: Rasterizer | None = None
        self._animation_pipeline = AnimationPipeline(trace_writer=self._trace_writer)
        self._text_renderer: DrawingMLTextRenderer | None = None
        self._shape_renderer: DrawingMLShapeRenderer | None = None
        self._scene_metadata: dict[str, Any] | None = None
        self._scene_background_color: str | None = None
        if SKIA_AVAILABLE:  # pragma: no branch
            try:
                self._rasterizer = Rasterizer()
            except Exception:  # pragma: no cover - defensive
                self._rasterizer = None
        self._tracer: ConversionTracer | None = None

    @property
    def _assets(self) -> AssetRegistry:
        if self._asset_registry is None:
            raise RuntimeError("Asset registry not initialised for current rendering run.")
        return self._asset_registry

    @property
    def _scene_background_color(self):
        return self._asset_pipeline._scene_background_color

    @_scene_background_color.setter
    def _scene_background_color(self, value):
        self._asset_pipeline._scene_background_color = value

    @property
    def _emf_manager(self):
        return self._asset_pipeline.emf_manager

    @property
    def _next_media_index(self):
        return self._asset_pipeline.next_media_index

    @_next_media_index.setter
    def _next_media_index(self, value):
        self._asset_pipeline.next_media_index = value

    def set_image_service(self, image_service: ImageService | None) -> None:
        """Update the image service used for on-the-fly media resolution."""
        self._image_service = image_service
        self._asset_pipeline.set_image_service(image_service)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_scene(
        self,
        scene: SceneGraph,
        *,
        slide_size: tuple[int, int] | None = None,
        tracer: ConversionTracer | None = None,
        animation_payload: dict[str, Any] | None = None,
    ) -> DrawingMLRenderResult:
        """Return slide XML and collected assets for the supplied scene graph."""

        prev_tracer = self._tracer
        self._tracer = tracer
        self._asset_registry = AssetRegistry()
        self._navigation.reset(self._assets)
        scene_background_color = getattr(scene, "background_color", None)
        if scene_background_color is None:
            scene_background_color = self._scene_background_color
        self._asset_pipeline.reset(
            assets=self._assets,
            trace_writer=self._trace_writer,
            scene_background_color=scene_background_color,
        )
        self._mask_pipeline.reset(assets=self._assets, tracer=self._tracer)
        self._animation_pipeline.reset(animation_payload, tracer=self._tracer)
        self._text_renderer = DrawingMLTextRenderer(
            text_template=self._text_template,
            wordart_template=self._wordart_template,
            policy_for=self._policy_for,
            register_run_navigation=self._navigation.register_run_navigation,
            trace_writer=self._trace_writer,
            assets=self._assets,
            logger=logger,
        )
        self._shape_renderer = DrawingMLShapeRenderer(
            rectangle_template=self._rectangle_template,
            preset_template=self._preset_template,
            path_template=self._path_template,
            line_template=self._line_template,
            picture_template=self._picture_template,
            path_generator=self._path_generator,
            policy_for=self._policy_for,
            register_media=self._register_media,
            trace_writer=self._trace_writer,
            animation_pipeline=self._animation_pipeline,
            rasterizer=self._rasterizer,
            logger=logger,
        )
        self._trace_writer("render_start", metadata={"slide_size": slide_size})
        try:
            fragments, next_shape_id = self._render_elements(scene, next_id=2)
            self._max_shape_id = next_shape_id - 1
            placeholder = "<!-- SHAPES WILL BE INSERTED HERE -->"
            slide_width, slide_height = slide_size or DEFAULT_SLIDE_SIZE
            shape_xml = tuple(fragments)

            slide_xml = self._slide_template.replace("{SLIDE_WIDTH}", str(slide_width))
            slide_xml = slide_xml.replace("{SLIDE_HEIGHT}", str(slide_height))
            slide_xml = slide_xml.replace("{OFFICE_PROFILE_XMLNS}", "")
            slide_xml = slide_xml.replace("{OFFICE_PROFILE_IGNORABLE}", "")
            shapes_xml = "\n            ".join(shape_xml)

            # 2. Inject shapes into template fragments
            slide_xml = slide_xml.replace(placeholder, shapes_xml)
            animation_xml = self._build_animation_xml()
            if animation_xml:
                slide_xml = slide_xml.replace("</p:sld>", f"{animation_xml}\n</p:sld>")
            result = DrawingMLRenderResult(
                slide_xml=slide_xml,
                slide_size=(slide_width, slide_height),
                assets=self._assets.snapshot(),
                shape_xml=shape_xml,
            )
            self._trace_writer(
                "render_complete",
                metadata={
                    "fragment_count": len(fragments),
                    "media_assets": len(result.assets.media),
                    "mask_assets": len(result.assets.masks),
                    "font_plans": len(result.assets.fonts),
                },
            )
            return result
        finally:
            self._asset_registry = None
            self._navigation.reset(None)
            self._mask_pipeline.clear()
            self._text_renderer = None
            self._shape_renderer = None
            self._animation_pipeline.reset(None)
            self._tracer = prev_tracer

    def render_shapes(
        self,
        scene: SceneGraph,
        *,
        slide_size: tuple[int, int] | None = None,
        tracer: ConversionTracer | None = None,
        animation_payload: dict[str, Any] | None = None,
    ) -> tuple[str, ...]:
        """Return serialized DrawingML shape fragments for the supplied scene graph."""

        return self.render_scene(
            scene,
            slide_size=slide_size,
            tracer=tracer,
            animation_payload=animation_payload,
        ).shape_xml

    def render_scene_from_ir(
        self,
        scene: IRScene,
        *,
        default_slide_size: tuple[int, int] = DEFAULT_SLIDE_SIZE,
        tracer: ConversionTracer | None = None,
        animation_payload: dict[str, Any] | None = None,
        animations: list | None = None,
    ) -> DrawingMLRenderResult:
        """Convenience wrapper that derives slide size from an IRScene."""

        slide_size, payload = self._scene_render_args_from_ir(
            scene,
            default_slide_size=default_slide_size,
            animation_payload=animation_payload,
            animations=animations,
        )
        prev_scene_metadata = self._scene_metadata
        prev_scene_background_color = self._scene_background_color
        self._scene_metadata = scene.metadata if isinstance(scene.metadata, dict) else None
        self._scene_background_color = scene.background_color or "FFFFFF"
        try:
            result = self.render_scene(
                scene.elements,
                slide_size=slide_size,
                tracer=tracer,
                animation_payload=payload,
            )
            return result._apply_background(scene.background_color)
        finally:
            self._scene_metadata = prev_scene_metadata
            self._scene_background_color = prev_scene_background_color

    def render_shapes_from_ir(
        self,
        scene: IRScene,
        *,
        default_slide_size: tuple[int, int] = DEFAULT_SLIDE_SIZE,
        tracer: ConversionTracer | None = None,
        animation_payload: dict[str, Any] | None = None,
        animations: list | None = None,
    ) -> tuple[str, ...]:
        """Convenience wrapper that derives slide size from an IRScene and returns shape fragments."""

        slide_size, payload = self._scene_render_args_from_ir(
            scene,
            default_slide_size=default_slide_size,
            animation_payload=animation_payload,
            animations=animations,
        )
        prev_scene_metadata = self._scene_metadata
        prev_scene_background_color = self._scene_background_color
        self._scene_metadata = scene.metadata if isinstance(scene.metadata, dict) else None
        self._scene_background_color = scene.background_color or "FFFFFF"
        try:
            return self.render_shapes(
                scene.elements,
                slide_size=slide_size,
                tracer=tracer,
                animation_payload=payload,
            )
        finally:
            self._scene_metadata = prev_scene_metadata
            self._scene_background_color = prev_scene_background_color

    def _scene_render_args_from_ir(
        self,
        scene: IRScene,
        *,
        default_slide_size: tuple[int, int],
        animation_payload: dict[str, Any] | None,
        animations: list | None,
    ) -> tuple[tuple[int, int], dict[str, Any]]:
        """Resolve slide sizing and animation payload for IR-scene rendering."""

        width_px = scene.width_px or 0.0
        height_px = scene.height_px or 0.0
        if width_px <= 0 or height_px <= 0:
            slide_size = default_slide_size
        else:
            slide_size = (px_to_emu(width_px), px_to_emu(height_px))

        payload = animation_payload or {}
        if animations is not None:
            # If animations are explicitly passed, use them
            # but preserve policy from the original payload
            new_payload: dict[str, Any] = {"definitions": animations}
            if isinstance(animation_payload, dict) and "policy" in animation_payload:
                new_payload["policy"] = animation_payload["policy"]
            payload = new_payload
        elif scene.animations:
            # Use scene animations, but preserve policy from animation_payload
            new_payload = {"definitions": scene.animations}
            if isinstance(animation_payload, dict) and "policy" in animation_payload:
                new_payload["policy"] = animation_payload["policy"]
            payload = new_payload

        return slide_size, payload

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
        if not (
            normalized.startswith("tests/svg/")
            or "/tests/svg/" in normalized
        ):
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
        source_metadata = getattr(element, "metadata", None)
        if isinstance(source_metadata, dict):
            metadata = dict(source_metadata)
            mask_metadata = metadata.get("mask")
            if isinstance(mask_metadata, dict):
                metadata["mask"] = dict(mask_metadata)
            try:
                element = replace(element, metadata=metadata)
            except TypeError:
                pass
            self.register_filter_assets(metadata)
        else:
            metadata = {}
        self._animation_pipeline.register_mapping(metadata, shape_id)

        # Collect clip bounds + diagnostics (non-standard XML no longer emitted).
        clip_bounds, clip_diags = clip_bounds_for(getattr(element, "clip", None))
        _mask_xml, mask_diags = self._mask_pipeline.render(element)

        # Store clip bounds in metadata for xfrm approximation by renderers.
        if clip_bounds is not None and isinstance(metadata, dict):
            metadata["_clip_bounds"] = clip_bounds

        if _mask_xml == "<!-- HIDDEN -->":
            if hasattr(element, "opacity"):
                try:
                    element = replace(element, opacity=0.0)
                except TypeError:
                    pass

        # Uniform opacity mask shortcut: multiply alpha into fill/stroke.
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
        hyperlink_xml = ""

        if isinstance(metadata, dict) and not isinstance(element, Group):
            hyperlink_xml = self._navigation.from_metadata(metadata, scope="shape") or ""

        if isinstance(element, TextFrame):
            if self._text_renderer is None:
                raise RuntimeError("Text renderer not initialised for current rendering run.")
            fragment, next_id = self._text_renderer.render(
                element,
                shape_id,
                hyperlink_xml=hyperlink_xml,
            )
            return [fragment], next_id
        if isinstance(element, Group):
            if hyperlink_xml:
                if self._assets is not None:
                    self._assets.add_diagnostic("Group-level navigation is not yet supported; hyperlink ignored.")
                logger.warning("Navigation on group elements is not supported; skipping hyperlink metadata.")

            filter_fallback_fragment = self._render_group_filter_fallback(
                element,
                shape_id,
                metadata,
            )
            if filter_fallback_fragment is not None:
                self._trace_writer(
                    "group_filter_fallback_rendered",
                    stage="filter",
                    metadata={"shape_id": shape_id},
                )
                return [filter_fallback_fragment], shape_id + 1

            # Group opacity with overlapping children: rasterize to avoid
            # double-blending artifacts from per-child alpha application.
            if (
                element.opacity < 1.0
                and self._rasterizer is not None
                and children_overlap(element.children)
            ):
                raster = self._rasterizer.rasterize(element)
                if raster is not None:
                    fragment = self._emit_raster_group(
                        raster, element, shape_id, metadata,
                    )
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
                        return [fragment], shape_id + 1

            if should_flatten_group_for_native_animation(
                element,
                self._animation_pipeline.metadata_targets_animation,
            ):
                self._trace_writer(
                    "group_flattened",
                    stage="writer",
                    metadata={
                        "shape_id": shape_id,
                        "reason": "native_animation_target",
                    },
                )
                fragments, next_id = self._render_elements(
                    element.children, shape_id,
                )
                if not fragments:
                    return None
                return fragments, next_id

            # Emit <p:grpSp> when the group has nested groups (preserves
            # z-order across sibling sub-trees). Flatten leaf groups that
            # only contain shapes — avoids unnecessary nesting.
            has_nested_groups = any(
                isinstance(c, Group) for c in element.children
            )

            if not has_nested_groups and not self._animation_pipeline.metadata_targets_animation(element.metadata):
                children = element.children
                if (
                    not can_remove_group_wrapper(element)
                    or metadata_has_bookmark_navigation(metadata)
                    or metadata.get("navigation") is not None
                ):
                    children = apply_group_wrapper_semantics(element, metadata)
                fragments, next_id = self._render_elements(
                    children, shape_id,
                )
                if not fragments:
                    return None
                return fragments, next_id

            group_bbox = element.bbox
            local_children = [
                translate_group_child_to_local_coordinates(
                    child,
                    group_bbox.x,
                    group_bbox.y,
                )
                for child in element.children
            ]
            child_fragments, next_id = self._render_elements(
                local_children, shape_id + 1,
            )
            if not child_fragments:
                return None

            children_xml = "\n".join(child_fragments)
            group_xml = (
                f'<p:grpSp>'
                f'<p:nvGrpSpPr>'
                f'<p:cNvPr id="{shape_id}" name="Group {shape_id}"/>'
                f'<p:cNvGrpSpPr/>'
                f'<p:nvPr/>'
                f'</p:nvGrpSpPr>'
                f'<p:grpSpPr>'
                f'{group_xfrm_xml(element)}'
                f'</p:grpSpPr>'
                f'{children_xml}'
                f'</p:grpSp>'
            )
            return [group_xml], next_id

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
        return self._animation_pipeline.build(max_shape_id=getattr(self, '_max_shape_id', 0))


__all__ = ["DrawingMLWriter", "DrawingMLRenderResult", "DEFAULT_SLIDE_SIZE", "EMU_PER_PX"]
