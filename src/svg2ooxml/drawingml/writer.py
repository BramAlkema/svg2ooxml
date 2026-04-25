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
from .mask_pipeline import MaskPipeline
from .navigation import register_navigation
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


def _children_overlap(children) -> bool:
    """Return True if any two children have overlapping bounding boxes."""
    bboxes = []
    for child in children:
        bbox = getattr(child, "bbox", None)
        if bbox is not None and bbox.width > 0 and bbox.height > 0:
            bboxes.append(bbox)
    for i in range(len(bboxes)):
        for j in range(i + 1, len(bboxes)):
            a, b = bboxes[i], bboxes[j]
            if (a.x < b.x + b.width and a.x + a.width > b.x
                    and a.y < b.y + b.height and a.y + a.height > b.y):
                return True
    return False


def _element_ids_for(element: object) -> set[str]:
    element_ids: set[str] = set()
    metadata = getattr(element, "metadata", None)
    if isinstance(metadata, dict):
        ids = metadata.get("element_ids")
        if isinstance(ids, list):
            element_ids.update(
                str(element_id) for element_id in ids if isinstance(element_id, str)
            )
    element_id = getattr(element, "element_id", None)
    if isinstance(element_id, str) and element_id:
        element_ids.add(element_id)
    return element_ids


def _apply_mask_alpha(element, alpha: float):
    """Multiply mask alpha into an element's fill and stroke paint opacities.

    Used for uniform-opacity masks where the mask is equivalent to reducing
    the element's overall alpha.  This avoids complex mask geometry and matches
    PowerPoint's "Convert to Shape" behavior for simple opacity masks.
    """
    from svg2ooxml.ir.paint import (
        LinearGradientPaint,
        RadialGradientPaint,
        SolidPaint,
    )

    def _scale_stops(stops, a: float):
        return [
            replace(s, opacity=s.opacity * a)
            for s in stops
        ]

    fill = getattr(element, "fill", None)
    new_fill = fill
    if isinstance(fill, SolidPaint):
        new_fill = replace(fill, opacity=fill.opacity * alpha)
    elif isinstance(fill, (LinearGradientPaint, RadialGradientPaint)):
        new_fill = replace(fill, stops=_scale_stops(fill.stops, alpha))

    stroke = getattr(element, "stroke", None)
    new_stroke = stroke
    if stroke is not None:
        paint = getattr(stroke, "paint", None)
        if isinstance(paint, SolidPaint):
            new_stroke = replace(stroke, paint=replace(paint, opacity=paint.opacity * alpha))
        elif isinstance(paint, (LinearGradientPaint, RadialGradientPaint)):
            new_stroke = replace(stroke, paint=replace(paint, stops=_scale_stops(paint.stops, alpha)))

    try:
        element = replace(element, fill=new_fill, stroke=new_stroke, mask=None, mask_instance=None)
    except TypeError:
        # Element may not have all fields; try partial replacement.
        try:
            element = replace(element, fill=new_fill, stroke=new_stroke)
        except TypeError:
            pass
    return element


def _translate_group_child_to_local_coordinates(element, dx: float, dy: float):
    """Return a copy of *element* translated by ``(-dx, -dy)`` for grpSp output.

    PowerPoint group children live in the group's child coordinate space, not
    the slide coordinate space. Rendering preserved groups with slide-absolute
    child offsets is tolerated for static layout but breaks grouped animation
    playback. This helper localises geometry only for XML emission; the source
    scene and animation metadata remain in slide space.
    """
    if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
        return element

    from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect
    from svg2ooxml.ir.scene import Group as IRGroup
    from svg2ooxml.ir.scene import Image as IRImage
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Circle, Ellipse, Line, Polygon, Polyline, Rectangle
    from svg2ooxml.ir.text import TextFrame as IRTextFrame

    def _move_point(point: Point) -> Point:
        return Point(point.x - dx, point.y - dy)

    def _move_rect(rect: Rect) -> Rect:
        return Rect(rect.x - dx, rect.y - dy, rect.width, rect.height)

    if isinstance(element, IRGroup):
        return replace(
            element,
            children=[
                _translate_group_child_to_local_coordinates(child, dx, dy)
                for child in element.children
            ],
        )
    if isinstance(element, IRPath):
        moved_segments = []
        for segment in element.segments:
            if isinstance(segment, LineSegment):
                moved_segments.append(
                    LineSegment(
                        start=_move_point(segment.start),
                        end=_move_point(segment.end),
                    )
                )
            elif isinstance(segment, BezierSegment):
                moved_segments.append(
                    BezierSegment(
                        start=_move_point(segment.start),
                        control1=_move_point(segment.control1),
                        control2=_move_point(segment.control2),
                        end=_move_point(segment.end),
                    )
                )
            else:
                moved_segments.append(segment)
        return replace(element, segments=moved_segments)
    if isinstance(element, Rectangle):
        return replace(element, bounds=_move_rect(element.bounds))
    if isinstance(element, Circle):
        return replace(element, center=_move_point(element.center))
    if isinstance(element, Ellipse):
        return replace(element, center=_move_point(element.center))
    if isinstance(element, Line):
        return replace(
            element,
            start=_move_point(element.start),
            end=_move_point(element.end),
        )
    if isinstance(element, Polyline):
        return replace(element, points=[_move_point(point) for point in element.points])
    if isinstance(element, Polygon):
        return replace(element, points=[_move_point(point) for point in element.points])
    if isinstance(element, IRTextFrame):
        return replace(
            element,
            origin=_move_point(element.origin),
            bbox=_move_rect(element.bbox),
        )
    if isinstance(element, IRImage):
        return replace(element, origin=_move_point(element.origin))
    return element


def _multiply_element_opacity(element, opacity: float):
    if opacity >= 0.999:
        return element
    current = getattr(element, "opacity", None)
    if not isinstance(current, (int, float)):
        return element
    try:
        return replace(element, opacity=max(0.0, min(1.0, float(current) * opacity)))
    except TypeError:
        return element


def _metadata_with_group_semantics(
    child_metadata: object,
    group_metadata: dict[str, object],
) -> dict[str, object]:
    metadata = dict(child_metadata) if isinstance(child_metadata, dict) else {}
    clip_bounds = group_metadata.get("_clip_bounds")
    if clip_bounds is not None and "_clip_bounds" not in metadata:
        metadata["_clip_bounds"] = clip_bounds
    navigation = group_metadata.get("navigation")
    if navigation is not None and "navigation" not in metadata:
        metadata["navigation"] = navigation
    return metadata


def _apply_group_wrapper_semantics_to_child(
    child,
    group: Group,
    group_metadata: dict[str, object],
):
    wrapped = _multiply_element_opacity(child, group.opacity)
    metadata = _metadata_with_group_semantics(
        getattr(wrapped, "metadata", None),
        group_metadata,
    )
    try:
        return replace(wrapped, metadata=metadata)
    except TypeError:
        return wrapped


def _apply_group_wrapper_semantics(
    group: Group,
    group_metadata: dict[str, object],
) -> list:
    return [
        _apply_group_wrapper_semantics_to_child(child, group, group_metadata)
        for child in group.children
    ]


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
        self._next_navigation_index = 1
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
        self._next_navigation_index = 1
        self._asset_pipeline.reset(
            assets=self._assets,
            trace_writer=self._trace_writer,
            scene_background_color=getattr(scene, 'background_color', None),
        )
        self._mask_pipeline.reset(assets=self._assets, tracer=self._tracer)
        self._animation_pipeline.reset(animation_payload, tracer=self._tracer)
        self._text_renderer = DrawingMLTextRenderer(
            text_template=self._text_template,
            wordart_template=self._wordart_template,
            policy_for=self._policy_for,
            register_run_navigation=self._register_run_navigation,
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
        return self.render_shapes(
            scene.elements,
            slide_size=slide_size,
            tracer=tracer,
            animation_payload=payload,
        )

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
        return "test-frame" in _element_ids_for(element)

    @staticmethod
    def _group_xfrm_xml(group: Group) -> str:
        bbox = group.bbox
        x = px_to_emu(bbox.x)
        y = px_to_emu(bbox.y)
        width = px_to_emu(bbox.width)
        height = px_to_emu(bbox.height)
        return (
            f'<a:xfrm>'
            f'<a:off x="{x}" y="{y}"/>'
            f'<a:ext cx="{width}" cy="{height}"/>'
            f'<a:chOff x="0" y="0"/>'
            f'<a:chExt cx="{width}" cy="{height}"/>'
            f'</a:xfrm>'
        )

    @staticmethod
    def _can_remove_group_wrapper(group: Group) -> bool:
        if abs(group.opacity - 1.0) > 1e-9:
            return False
        if group.clip is not None or group.mask is not None or group.mask_instance is not None:
            return False
        metadata = group.metadata if isinstance(group.metadata, dict) else {}
        if metadata.get("filters") or metadata.get("filter_metadata"):
            return False
        return True

    def _group_directly_targets_animation(self, group: Group) -> bool:
        return self._animation_pipeline.metadata_targets_animation(group.metadata)

    def _should_flatten_group_for_native_animation(self, group: Group) -> bool:
        if not self._can_remove_group_wrapper(group):
            return False
        if self._group_directly_targets_animation(group):
            return False
        return self._group_contains_bookmark_navigation(
            group
        ) or self._group_contains_animation_target(group)

    def _group_contains_animation_target(self, group: Group) -> bool:
        if self._animation_pipeline.metadata_targets_animation(group.metadata):
            return True
        for child in group.children:
            metadata = getattr(child, "metadata", None)
            if self._animation_pipeline.metadata_targets_animation(metadata):
                return True
            if isinstance(child, Group) and self._group_contains_animation_target(child):
                return True
        return False

    @staticmethod
    def _group_contains_bookmark_navigation(group: Group) -> bool:
        if DrawingMLWriter._metadata_has_bookmark_navigation(group.metadata):
            return True
        for child in group.children:
            metadata = getattr(child, "metadata", None)
            if DrawingMLWriter._metadata_has_bookmark_navigation(metadata):
                return True
            if isinstance(child, Group) and DrawingMLWriter._group_contains_bookmark_navigation(child):
                return True
        return False

    @staticmethod
    def _metadata_has_bookmark_navigation(metadata: object) -> bool:
        if not isinstance(metadata, dict):
            return False
        navigation = metadata.get("navigation")
        if navigation is None:
            return False
        entries = navigation if isinstance(navigation, list) else [navigation]
        for entry in entries:
            if isinstance(entry, dict) and entry.get("kind") == "bookmark":
                return True
        return False

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
        metadata = getattr(element, "metadata", None)
        if isinstance(metadata, dict):
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
            hyperlink_xml = self._navigation_from_metadata(metadata, scope="shape") or ""

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
                and _children_overlap(element.children)
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

            if self._should_flatten_group_for_native_animation(element):
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

            if not has_nested_groups and not self._group_directly_targets_animation(element):
                children = element.children
                if (
                    not self._can_remove_group_wrapper(element)
                    or self._metadata_has_bookmark_navigation(metadata)
                    or metadata.get("navigation") is not None
                ):
                    children = _apply_group_wrapper_semantics(element, metadata)
                fragments, next_id = self._render_elements(
                    children, shape_id,
                )
                if not fragments:
                    return None
                return fragments, next_id

            group_bbox = element.bbox
            local_children = [
                _translate_group_child_to_local_coordinates(
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
                f'{self._group_xfrm_xml(element)}'
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

    def _register_run_navigation(self, navigation, text_segment: str):
        return self._register_navigation_asset(navigation, scope="text_run", text=text_segment)

    def _navigation_from_metadata(self, metadata: dict[str, object], *, scope: str) -> str:
        nav_data = metadata.get("navigation")
        if nav_data is None:
            return ""
        entries = nav_data if isinstance(nav_data, list) else [nav_data]
        for entry in entries:
            elem = self._register_navigation_asset(entry, scope=scope)
            if elem is not None:
                from .xml_builder import to_string as _ts
                return _ts(elem)
        return ""

    def _register_navigation_asset(self, navigation, *, scope: str, text: str | None = None):
        if navigation is None or self._asset_registry is None:
            return None

        return register_navigation(
            navigation,
            scope=scope,
            text=text,
            allocate_rel_id=self._allocate_navigation_rid,
            add_asset=lambda asset: self._assets.add_navigation(
                relationship_id=asset.relationship_id,
                relationship_type=asset.relationship_type,
                target=asset.target,
                target_mode=asset.target_mode,
                action=asset.action,
                tooltip=asset.tooltip,
                history=asset.history,
                scope=asset.scope,
                text=asset.text,
            ),
        )

    def _emit_raster_group(self, raster, group, shape_id, metadata) -> str | None:
        return self._asset_pipeline.emit_raster_group(raster, group, shape_id, metadata)

    def _build_animation_xml(self) -> str:
        return self._animation_pipeline.build(max_shape_id=getattr(self, '_max_shape_id', 0))

    def _allocate_navigation_rid(self) -> str:
        rid = f"rIdNav{self._next_navigation_index}"
        self._next_navigation_index += 1
        return rid


__all__ = ["DrawingMLWriter", "DrawingMLRenderResult", "DEFAULT_SLIDE_SIZE", "EMU_PER_PX"]
