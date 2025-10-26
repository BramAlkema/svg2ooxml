"""DrawingML writer that renders IR scenes to slide XML fragments."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Tuple, TYPE_CHECKING

from svg2ooxml.io.emf import EMFRelationshipManager
from svg2ooxml.ir.animation import AnimationDefinition
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.scene import ClipRef, Group, Image, MaskRef, Path as IRPath, SceneGraph
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle, Line, Polygon, Polyline
from svg2ooxml.ir.text import TextFrame
from svg2ooxml.map.converter.core import IRScene
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_RASTERIZE

from . import paint_runtime, shapes_runtime
from .assets import AssetRegistry
from .animation_writer import DrawingMLAnimationWriter
from .clipmask import clip_xml_for
from .image import render_picture
from .generator import DrawingMLPathGenerator, EMU_PER_PX, px_to_emu
from .navigation import register_navigation
from .result import DrawingMLRenderResult
from .mask_store import MaskAssetStore
from .mask_writer import MaskWriter
from .rasterizer import Rasterizer, SKIA_AVAILABLE

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.map.tracer import ConversionTracer

DEFAULT_SLIDE_SIZE = (9144000, 6858000)  # 10" x 7.5"

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _assets_root() -> Path:
    return _project_root() / "assets" / "pptx_templates"


class DrawingMLWriter:
    """Render IR scene graphs into DrawingML shape fragments."""

    def __init__(self, *, template_dir: Path | None = None) -> None:
        self._template_dir = template_dir or _assets_root()
        self._slide_template = (self._template_dir / "slide_template.xml").read_text(encoding="utf-8")
        self._text_template = (self._template_dir / "text_shape_template.xml").read_text(encoding="utf-8")
        self._rectangle_template = (self._template_dir / "shape_rectangle.xml").read_text(encoding="utf-8")
        self._preset_template = (self._template_dir / "shape_preset.xml").read_text(encoding="utf-8")
        self._path_template = (self._template_dir / "shape_path.xml").read_text(encoding="utf-8")
        self._line_template = (self._template_dir / "shape_line.xml").read_text(encoding="utf-8")
        self._picture_template = (self._template_dir / "picture_shape.xml").read_text(encoding="utf-8")
        self._wordart_template = (self._template_dir / "wordart_shape_template.xml").read_text(encoding="utf-8")
        self._path_generator = DrawingMLPathGenerator()
        self._emf_manager = EMFRelationshipManager()
        self._asset_registry: AssetRegistry | None = None
        self._next_media_index = 1
        self._next_navigation_index = 1
        self._seen_filter_assets: set[str] = set()
        self._mask_writer: MaskWriter | None = None
        self._mask_store_factory = MaskAssetStore
        self._rasterizer: Rasterizer | None = None
        self._animation_writer = DrawingMLAnimationWriter()
        self._animation_payload: dict[str, Any] | None = None
        self._animation_shape_map: dict[str, str] = {}
        self._animation_policy: dict[str, object] | None = None
        if SKIA_AVAILABLE:  # pragma: no branch
            try:
                self._rasterizer = Rasterizer()
            except Exception:  # pragma: no cover - defensive
                self._rasterizer = None
        self._tracer: "ConversionTracer | None" = None

    @property
    def _assets(self) -> AssetRegistry:
        if self._asset_registry is None:
            raise RuntimeError("Asset registry not initialised for current rendering run.")
        return self._asset_registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_scene(
        self,
        scene: SceneGraph,
        *,
        slide_size: Tuple[int, int] | None = None,
        tracer: "ConversionTracer | None" = None,
        animation_payload: dict[str, Any] | None = None,
    ) -> DrawingMLRenderResult:
        """Return slide XML and collected assets for the supplied scene graph."""

        prev_tracer = self._tracer
        self._tracer = tracer
        self._asset_registry = AssetRegistry()
        self._next_media_index = 1
        self._next_navigation_index = 1
        self._seen_filter_assets.clear()
        self._emf_manager.reset()
        mask_store = self._mask_store_factory()
        self._mask_writer = MaskWriter(mask_store=mask_store, tracer=self._tracer)
        self._mask_writer.bind_assets(self._asset_registry)
        self._trace_writer("render_start", metadata={"slide_size": slide_size})
        self._animation_payload = animation_payload
        self._animation_shape_map = {}
        self._animation_policy = {}
        if isinstance(self._animation_payload, dict):
            payload_policy = self._animation_payload.get("policy")
            if isinstance(payload_policy, dict):
                self._animation_policy = dict(payload_policy)
        try:
            fragments, _ = self._render_elements(scene, next_id=2)
            placeholder = "<!-- SHAPES WILL BE INSERTED HERE -->"
            slide_width, slide_height = slide_size or DEFAULT_SLIDE_SIZE

            slide_xml = self._slide_template.replace("cx=\"9144000\"", f'cx="{slide_width}"')
            slide_xml = slide_xml.replace("cy=\"6858000\"", f'cy="{slide_height}"')
            shapes_xml = "\n            ".join(fragments)
            slide_xml = slide_xml.replace(placeholder, shapes_xml)
            animation_xml = self._build_animation_xml()
            if animation_xml:
                slide_xml = slide_xml.replace("</p:sld>", f"{animation_xml}\n</p:sld>")
            result = DrawingMLRenderResult(
                slide_xml=slide_xml,
                slide_size=(slide_width, slide_height),
                assets=self._assets.snapshot(),
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
            self._mask_writer = None
            self._tracer = prev_tracer
            self._animation_payload = None
            self._animation_shape_map = {}
            self._animation_policy = None

    def render_scene_from_ir(
        self,
        scene: IRScene,
        *,
        default_slide_size: Tuple[int, int] = DEFAULT_SLIDE_SIZE,
        tracer: "ConversionTracer | None" = None,
        animation_payload: dict[str, Any] | None = None,
    ) -> DrawingMLRenderResult:
        """Convenience wrapper that derives slide size from an IRScene."""

        width_px = scene.width_px or 0.0
        height_px = scene.height_px or 0.0
        if width_px <= 0 or height_px <= 0:
            slide_size = default_slide_size
        else:
            slide_size = (px_to_emu(width_px), px_to_emu(height_px))
        return self.render_scene(
            scene.elements,
            slide_size=slide_size,
            tracer=tracer,
            animation_payload=animation_payload,
        )

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
            fragments.append(rendered[0])
            current_id = rendered[1]
        return fragments, current_id

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
        ext = image.format.lower()
        if ext == "emf":
            if not isinstance(image.data, (bytes, bytearray)):
                raise TypeError("EMF images require inline byte data")
            metadata = image.metadata if isinstance(image.metadata, dict) else {}
            emf_meta = metadata.get("emf_asset") if isinstance(metadata, dict) else None
            preferred_id = None
            width_emu = None
            height_emu = None
            if isinstance(emf_meta, dict):
                preferred_id = emf_meta.get("relationship_id")
                width_emu = self._maybe_int(emf_meta.get("width_emu"))
                height_emu = self._maybe_int(emf_meta.get("height_emu"))
            entry, is_new = self._emf_manager.register(
                bytes(image.data),
                rel_id=preferred_id,
                width_emu=width_emu,
                height_emu=height_emu,
            )
            if is_new:
                self._assets.add_media(
                    relationship_id=entry.relationship_id,
                    filename=entry.filename,
                    data=entry.data,
                    content_type="image/x-emf",
                    width_emu=entry.width_emu,
                    height_emu=entry.height_emu,
                    source="emf",
                )
            if isinstance(emf_meta, dict):
                emf_meta["relationship_id"] = entry.relationship_id
                if entry.width_emu is not None:
                    emf_meta["width_emu"] = entry.width_emu
                if entry.height_emu is not None:
                    emf_meta["height_emu"] = entry.height_emu
            self._trace_writer(
                "media_registered",
                stage="media",
                metadata={
                    "format": "emf",
                    "relationship_id": entry.relationship_id,
                    "new_asset": is_new,
                    "width_emu": entry.width_emu,
                    "height_emu": entry.height_emu,
                    "image_source": metadata.get("image_source"),
                },
            )
            return entry.relationship_id

        r_id = f"rId{self._next_media_index}"
        filename = f"image{self._next_media_index}.{ext}"
        content_type = self._content_type_for_format(ext)
        self._next_media_index += 1
        data = image.data if isinstance(image.data, (bytes, bytearray)) else bytes(image.data)
        self._assets.add_media(
            relationship_id=r_id,
            filename=filename,
            data=data,
            content_type=content_type,
            source="image",
        )
        metadata = image.metadata if isinstance(image.metadata, dict) else {}
        self._trace_writer(
            "media_registered",
            stage="media",
            metadata={
                "format": ext,
                "relationship_id": r_id,
                "width_px": getattr(image.size, "width", None),
                "height_px": getattr(image.size, "height", None),
                "image_source": metadata.get("image_source"),
                "data_bytes": len(data) if isinstance(data, (bytes, bytearray)) else len(bytes(data)),
            },
        )
        return r_id

    def register_filter_assets(self, metadata: dict[str, object] | None) -> None:
        if not isinstance(metadata, dict):
            return
        policy = metadata.get("policy")
        if not isinstance(policy, dict):
            return
        media_policy = policy.get("media")
        if not isinstance(media_policy, dict):
            return
        filter_assets = media_policy.get("filter_assets")
        if not isinstance(filter_assets, dict):
            return

        for assets in filter_assets.values():
            if not isinstance(assets, list):
                continue
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                data_hex = asset.get("data_hex")
                if not isinstance(data_hex, str) or not data_hex:
                    continue
                if data_hex in self._seen_filter_assets:
                    continue

                asset_type = asset.get("type")
                if asset_type == "emf":
                    binary = bytes.fromhex(data_hex)
                    preferred_id = asset.get("relationship_id")
                    if not isinstance(preferred_id, str) or not preferred_id:
                        preferred_id = None
                    width_emu = self._maybe_int(asset.get("width_emu"))
                    height_emu = self._maybe_int(asset.get("height_emu"))
                    entry, is_new = self._emf_manager.register(
                        binary,
                        rel_id=preferred_id,
                        width_emu=width_emu,
                        height_emu=height_emu,
                    )
                    asset["relationship_id"] = entry.relationship_id
                    if entry.width_emu is not None:
                        asset["width_emu"] = entry.width_emu
                    if entry.height_emu is not None:
                        asset["height_emu"] = entry.height_emu
                    if is_new:
                        self._assets.add_media(
                            relationship_id=entry.relationship_id,
                            filename=entry.filename,
                            data=entry.data,
                            content_type="image/x-emf",
                            width_emu=entry.width_emu,
                            height_emu=entry.height_emu,
                            source="filter",
                        )
                        self._trace_writer(
                            "filter_asset_registered",
                            stage="filter",
                            metadata={
                                "format": "emf",
                                "relationship_id": entry.relationship_id,
                                "width_emu": entry.width_emu,
                                "height_emu": entry.height_emu,
                            },
                        )
                    self._seen_filter_assets.add(data_hex)
                    continue

                ext = "png"
                content_type = "image/png"
                binary = bytes.fromhex(data_hex)
                rel_id = asset.get("relationship_id")
                if not isinstance(rel_id, str) or not rel_id:
                    rel_id = f"rId{self._next_media_index}"
                    asset["relationship_id"] = rel_id
                filename = f"media_{self._next_media_index}.{ext}"
                self._next_media_index += 1
                self._assets.add_media(
                    relationship_id=rel_id,
                    filename=filename,
                    data=binary,
                    content_type=content_type,
                    source="filter",
                )
                self._trace_writer(
                    "filter_asset_registered",
                    stage="filter",
                    metadata={
                        "format": content_type,
                        "relationship_id": rel_id,
                    },
                )
                self._seen_filter_assets.add(data_hex)

    @staticmethod
    def _content_type_for_format(ext: str) -> str:
        mapping = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "svg": "image/svg+xml",
            "emf": "image/x-emf",
        }
        return mapping.get(ext, "application/octet-stream")

    @staticmethod
    def _maybe_int(value: object) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _render_element(self, element, shape_id: int) -> tuple[str, int] | None:
        metadata = getattr(element, "metadata", None)
        if isinstance(metadata, dict):
            self.register_filter_assets(metadata)
        else:
            metadata = {}
        self._register_animation_mapping(metadata, shape_id)

        clip_xml, clip_diags = clip_xml_for(getattr(element, "clip", None))
        mask_xml = ""
        mask_diags: list[str] = []
        if self._mask_writer is not None:
            mask_xml, mask_diags = self._mask_writer.render(element)
            if mask_xml:
                self._trace_writer(
                    "mask_applied",
                    stage="mask",
                    metadata={
                        "shape_id": shape_id,
                        "length": len(mask_xml),
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

        if isinstance(element, Rectangle):
            rasterized = self._maybe_rasterize(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_xml,
                mask_xml=mask_xml,
            )
            if rasterized is not None:
                return rasterized
            xml = shapes_runtime.render_rectangle(
                element,
                shape_id,
                template=self._rectangle_template,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Circle):
            rasterized = self._maybe_rasterize(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_xml,
                mask_xml=mask_xml,
            )
            if rasterized is not None:
                return rasterized
            xml = shapes_runtime.render_circle(
                element,
                shape_id,
                template=self._preset_template,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Ellipse):
            rasterized = self._maybe_rasterize(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_xml,
                mask_xml=mask_xml,
            )
            if rasterized is not None:
                return rasterized
            xml = shapes_runtime.render_ellipse(
                element,
                shape_id,
                template=self._preset_template,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Line):
            xml = shapes_runtime.render_line(
                element,
                shape_id,
                template=self._line_template,
                path_generator=self._path_generator,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                paint_to_fill=paint_runtime.paint_to_fill,
                policy_for=self._policy_for,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Polyline):
            xml = shapes_runtime.render_polyline(
                element,
                shape_id,
                template=self._path_template,
                path_generator=self._path_generator,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                policy_for=self._policy_for,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Polygon):
            xml = shapes_runtime.render_polygon(
                element,
                shape_id,
                template=self._path_template,
                path_generator=self._path_generator,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                policy_for=self._policy_for,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, IRPath):
            rasterized = self._maybe_rasterize(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_xml,
                mask_xml=mask_xml,
            )
            if rasterized is not None:
                return rasterized
            xml = shapes_runtime.render_path(
                element,
                shape_id,
                template=self._path_template,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                path_generator=self._path_generator,
                policy_for=self._policy_for,
                logger=logger,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, TextFrame):
            candidate = getattr(element, "wordart_candidate", None)
            metadata = element.metadata if isinstance(element.metadata, dict) else {}
            wordart_meta = metadata.get("wordart") if isinstance(metadata, dict) else {}
            prefer_native = True
            if isinstance(wordart_meta, dict):
                prefer_native = bool(wordart_meta.get("prefer_native", True))

            if (
                candidate is not None
                and getattr(candidate, "is_confident", False)
                and prefer_native
            ):
                xml = shapes_runtime.render_wordart(
                    element,
                    candidate,
                    shape_id,
                    template=self._wordart_template,
                    policy_for=self._policy_for,
                    logger=logger,
                    hyperlink_xml=hyperlink_xml,
                    clip_path_xml=clip_xml,
                    mask_xml=mask_xml,
                    register_run_navigation=self._register_run_navigation,
                )
            else:
                xml = shapes_runtime.render_textframe(
                    element,
                    shape_id,
                    template=self._text_template,
                    policy_for=self._policy_for,
                    logger=logger,
                    hyperlink_xml=hyperlink_xml,
                    clip_path_xml=clip_xml,
                    mask_xml=mask_xml,
                    register_run_navigation=self._register_run_navigation,
                )

            if getattr(element, "embedding_plan", None) is not None:
                plan = element.embedding_plan
                if plan.requires_embedding:
                    self._assets.add_font_plan(shape_id=shape_id, plan=plan)
                    self._trace_writer(
                        "font_plan_registered",
                        stage="font",
                        metadata={
                            "shape_id": shape_id,
                            "font_family": getattr(plan, "font_family", None),
                            "requires_embedding": plan.requires_embedding,
                            "glyph_count": getattr(plan, "glyph_count", None),
                        },
                    )

            return xml, shape_id + 1
        if isinstance(element, Group):
            if hyperlink_xml:
                if self._assets is not None:
                    self._assets.add_diagnostic("Group-level navigation is not yet supported; hyperlink ignored.")
                logger.warning("Navigation on group elements is not supported; skipping hyperlink metadata.")
            fragments, next_id = self._render_elements(element.children, shape_id)
            if not fragments:
                return None
            return "\n".join(fragments), next_id
        if isinstance(element, Image):
            if element.data is None and element.href is None:
                logger.warning("Image element missing data and href; skipping image")
                return None
            if element.data is None:
                logger.warning("External image references not yet supported; skipping image")
                return None
            rendered = render_picture(
                element,
                shape_id,
                template=self._picture_template,
                policy_for=self._policy_for,
                register_media=self._register_media,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_xml,
                mask_xml=mask_xml,
            )
            if rendered is None:
                return None
            return rendered, shape_id + 1

        logger.debug("Skipping unsupported IR element type: %s", type(element).__name__)
        return None

    def _register_animation_mapping(self, metadata: dict[str, object] | None, shape_id: int) -> None:
        if not isinstance(metadata, dict):
            return
        element_ids = metadata.get("element_ids")
        if not isinstance(element_ids, list):
            return
        for element_id in element_ids:
            if isinstance(element_id, str):
                self._animation_shape_map.setdefault(element_id, str(shape_id))

    def _register_run_navigation(self, navigation, text_segment: str) -> str:
        return self._register_navigation_asset(navigation, scope="text_run", text=text_segment)

    def _navigation_from_metadata(self, metadata: dict[str, object], *, scope: str) -> str:
        nav_data = metadata.get("navigation")
        if nav_data is None:
            return ""
        entries = nav_data if isinstance(nav_data, list) else [nav_data]
        for entry in entries:
            xml = self._register_navigation_asset(entry, scope=scope)
            if xml:
                return xml
        return ""

    def _register_navigation_asset(self, navigation, *, scope: str, text: str | None = None) -> str:
        if navigation is None or self._asset_registry is None:
            return ""

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

    def _build_animation_xml(self) -> str:
        if not self._animation_payload:
            return ""

        definitions = self._animation_payload.get("definitions") or []
        timeline = self._animation_payload.get("timeline") or []
        if not definitions:
            return ""

        remapped: list[AnimationDefinition] = []
        tracer = self._tracer
        for definition in definitions:
            element_id = getattr(definition, "element_id", None)
            if not isinstance(element_id, str):
                self._trace_writer(
                    "invalid_animation_definition",
                    stage="animation",
                    metadata={"reason": "missing_element_id"},
                )
                continue
            shape_id = self._animation_shape_map.get(element_id)
            if not shape_id:
                self._trace_writer(
                    "unmapped_animation",
                    stage="animation",
                    metadata={
                        "element_id": element_id,
                        "animation_type": definition.animation_type.value,
                    },
                )
                continue
            remapped.append(replace(definition, element_id=shape_id))
            self._trace_writer(
                "mapped_animation",
                stage="animation",
                metadata={
                    "element_id": element_id,
                    "shape_id": shape_id,
                    "animation_type": definition.animation_type.value,
                },
            )

        if not remapped:
            if definitions:
                self._trace_writer(
                    "timing_skipped",
                    stage="animation",
                    metadata={"reason": "no_mapped_definitions", "animation_count": len(definitions)},
                )
            return ""

        animation_options = self._animation_policy or {}
        animation_xml = self._animation_writer.build(remapped, timeline, tracer=tracer, options=animation_options)
        if animation_xml:
            self._trace_writer(
                "timing_emitted",
                stage="animation",
                metadata={
                    "animation_count": len(remapped),
                    "timeline_frames": len(timeline),
                    "fallback_mode": animation_options.get("fallback_mode", "native"),
                },
            )
        else:
            self._trace_writer(
                "timing_skipped",
                stage="animation",
                metadata={
                    "reason": "writer_returned_empty",
                    "animation_count": len(remapped),
                    "fallback_mode": animation_options.get("fallback_mode", "native"),
                },
            )
        return animation_xml

    def _allocate_navigation_rid(self) -> str:
        rid = f"rIdNav{self._next_navigation_index}"
        self._next_navigation_index += 1
        return rid

    def _maybe_rasterize(
        self,
        element,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
        clip_path_xml: str,
        mask_xml: str,
    ) -> tuple[str, int] | None:
        if self._rasterizer is None:
            return None
        policy = metadata.setdefault("policy", {}) if isinstance(metadata, dict) else {}
        geometry_policy = policy.setdefault("geometry", {})
        fallback = geometry_policy.get("suggest_fallback")
        if fallback not in {FALLBACK_BITMAP, FALLBACK_RASTERIZE}:
            return None
        try:
            result = self._rasterizer.rasterize(element)
        except Exception:  # pragma: no cover - defensive
            logger.debug("Rasterization failed for %s", type(element).__name__, exc_info=True)
            return None
        if result is None:
            return None

        origin = Point(result.bounds.x, result.bounds.y)
        size_rect = Rect(0.0, 0.0, result.bounds.width, result.bounds.height)
        image_metadata = {
            "rasterized": True,
            "source_shape": type(element).__name__,
        }
        element_ids = metadata.get("element_ids") if isinstance(metadata, dict) else None
        if isinstance(element_ids, list):
            image_metadata["element_ids"] = list(element_ids)
            for element_id in element_ids:
                if isinstance(element_id, str):
                    self._animation_shape_map.setdefault(element_id, str(shape_id))
        raster_image = Image(
            origin=origin,
            size=size_rect,
            data=result.data,
            format="png",
            metadata=image_metadata,
        )
        xml = render_picture(
            raster_image,
            shape_id,
            template=self._picture_template,
            policy_for=self._policy_for,
            register_media=self._register_media,
            hyperlink_xml=hyperlink_xml,
            clip_path_xml=clip_path_xml,
            mask_xml=mask_xml,
        )
        if xml is None:
            return None
        geometry_policy.setdefault("rasterized_media", []).append({"shape_id": shape_id, "format": "png"})
        self._trace_writer(
            "geometry_rasterized",
            stage="media",
            metadata={
                "shape_id": shape_id,
                "format": "png",
                "source_shape": type(element).__name__,
            },
        )
        return xml, shape_id + 1






__all__ = ["DrawingMLWriter", "DrawingMLRenderResult", "DEFAULT_SLIDE_SIZE", "EMU_PER_PX"]
