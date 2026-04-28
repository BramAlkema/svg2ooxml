"""Public scene rendering methods for the DrawingML writer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from svg2ooxml.core.ir import IRScene
from svg2ooxml.ir.scene import SceneGraph

from .assets import AssetRegistry
from .generator import px_to_emu
from .result import DrawingMLRenderResult
from .shape_renderer import DrawingMLShapeRenderer
from .text_renderer import DrawingMLTextRenderer
from .writer_base import DEFAULT_SLIDE_SIZE, logger

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.tracing import ConversionTracer


class DrawingMLSceneMixin:
    """Render IR scenes into slide XML and shape fragments."""

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
            slide_xml, shape_xml, slide_dimensions = self._assemble_slide_xml(
                fragments,
                slide_size,
            )
            result = DrawingMLRenderResult(
                slide_xml=slide_xml,
                slide_size=slide_dimensions,
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

    def _assemble_slide_xml(
        self,
        fragments: list[str],
        slide_size: tuple[int, int] | None,
    ) -> tuple[str, tuple[str, ...], tuple[int, int]]:
        placeholder = "<!-- SHAPES WILL BE INSERTED HERE -->"
        slide_width, slide_height = slide_size or DEFAULT_SLIDE_SIZE
        shape_xml = tuple(fragments)

        slide_xml = self._slide_template.replace("{SLIDE_WIDTH}", str(slide_width))
        slide_xml = slide_xml.replace("{SLIDE_HEIGHT}", str(slide_height))
        slide_xml = slide_xml.replace("{OFFICE_PROFILE_XMLNS}", "")
        slide_xml = slide_xml.replace("{OFFICE_PROFILE_IGNORABLE}", "")
        slide_xml = slide_xml.replace(placeholder, "\n            ".join(shape_xml))
        animation_xml = self._build_animation_xml()
        if animation_xml:
            slide_xml = slide_xml.replace("</p:sld>", f"{animation_xml}\n</p:sld>")
        return slide_xml, shape_xml, (slide_width, slide_height)

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
            new_payload: dict[str, Any] = {"definitions": animations}
            if isinstance(animation_payload, dict) and "policy" in animation_payload:
                new_payload["policy"] = animation_payload["policy"]
            payload = new_payload
        elif scene.animations:
            new_payload = {"definitions": scene.animations}
            if isinstance(animation_payload, dict) and "policy" in animation_payload:
                new_payload["policy"] = animation_payload["policy"]
            payload = new_payload

        return slide_size, payload


__all__ = ["DrawingMLSceneMixin"]
