"""DrawingML mask writer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple, TYPE_CHECKING

from svg2ooxml.drawingml.mask_generator import compute_mask_geometry
from svg2ooxml.drawingml.raster_adapter import RasterAdapter
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.paint import SolidPaint
from svg2ooxml.ir.scene import MaskInstance, MaskRef
from svg2ooxml.drawingml.bridges import EMFPathAdapter, PathStyle
from svg2ooxml.common.units import UnitConverter

from .mask_store import MaskAssetStore

if TYPE_CHECKING:  # pragma: no cover - typing only
    from svg2ooxml.core.tracing import ConversionTracer


@dataclass
class MaskRenderResult:
    xml: str
    diagnostics: List[str]


@dataclass
class _MaskAttemptResult:
    success: bool
    xml: str = ""
    diagnostics: List[str] = field(default_factory=list)


class MaskWriter:
    """Render mask definitions for DrawingML shapes."""

    def __init__(self, *, mask_store: MaskAssetStore | None = None, tracer: "ConversionTracer | None" = None) -> None:
        # Stored for future use when native mask assets become supported.
        self._mask_store = mask_store or MaskAssetStore()
        self._assets = None
        self._unit_converter = UnitConverter()
        self._emf_adapter = EMFPathAdapter()
        self._raster_adapter = RasterAdapter()
        self._tracer = tracer

    def bind_assets(self, asset_registry) -> None:
        """Attach the slide asset registry."""

        self._assets = asset_registry

    def _trace_mask(
        self,
        action: str,
        *,
        metadata: dict[str, object] | None = None,
        subject: str | None = None,
    ) -> None:
        tracer = self._tracer
        if tracer is None:
            return
        tracer.record_stage_event(stage="mask", action=action, metadata=metadata, subject=subject)

    def render(self, element) -> Tuple[str, List[str]]:
        """Return mask XML and diagnostics for the supplied IR element."""

        mask_ref = getattr(element, "mask", None)
        if mask_ref is None:
            return "", []

        metadata = getattr(element, "metadata", None)
        mask_meta = {}
        if isinstance(metadata, dict):
            mask_meta = metadata.get("mask", {}) or {}

        strategy = mask_meta.get("strategy")
        classification = mask_meta.get("classification")
        diagnostics: list[str] = list(mask_meta.get("diagnostics", []))

        if strategy in {"emf", "policy_emf"}:
            # Continue through new fallback ladder below.
            pass

        if strategy in {"raster", "policy_raster"} or classification in {"raster", "mixed"}:
            # Continue through fallback ladder below.
            pass

        if strategy == "unsupported":
            if mask_ref.mask_id:
                diagnostics.append(f"Mask {mask_ref.mask_id} requires fallback; native mask not emitted.")
            return "", diagnostics

        mask_instance = getattr(element, "mask_instance", None)
        fallback_order = _fallback_sequence(mask_meta)
        geometry_result = None
        geometry_xml = mask_meta.get("geometry_xml")

        if geometry_xml is None or not str(geometry_xml).strip():
            geometry_result = compute_mask_geometry(mask_ref)
            if geometry_result is not None:
                diagnostics.extend(geometry_result.diagnostics)
                if geometry_result.geometry is not None and geometry_result.geometry.xml:
                    geometry_xml = geometry_result.geometry.xml
                    mask_meta.setdefault("geometry_xml", geometry_xml)
                    bounds = geometry_result.geometry.bounds
                    mask_meta.setdefault("bounds_px", (bounds.x, bounds.y, bounds.width, bounds.height))

        # Attempt ladder in policy order.
        attempts = {
            "native": lambda: self._attempt_native(mask_ref, mask_meta, mask_instance, geometry_xml),
            "mimic": lambda: self._attempt_mimic(mask_ref, mask_meta, mask_instance, geometry_result),
            "emf": lambda: self._attempt_emf(mask_ref, mask_meta, mask_instance, geometry_result),
            "policy_emf": lambda: self._attempt_emf(mask_ref, mask_meta, mask_instance, geometry_result, forced=True),
            "raster": lambda: self._attempt_raster(mask_ref, mask_meta, mask_instance, geometry_result),
            "policy_raster": lambda: self._attempt_raster(mask_ref, mask_meta, mask_instance, geometry_result, forced=True),
        }

        for mode in fallback_order:
            handler = attempts.get(mode)
            if handler is None:
                continue
            attempt = handler()
            diagnostics.extend(attempt.diagnostics)
            if attempt.success:
                mask_meta["applied_strategy"] = mode
                return attempt.xml, diagnostics

        if mask_ref.mask_id:
            diagnostics.append(f"Mask {mask_ref.mask_id} could not be emitted; all fallbacks failed.")
        else:
            diagnostics.append("Mask could not be emitted; all fallbacks failed.")
        return "", diagnostics

    def _build_vector_mask_fragment(
        self,
        mask_ref: MaskRef,
        geometry_xml: str,
        mask_meta: dict,
        mask_instance: MaskInstance | None,
    ) -> str:
        src_rect = self._src_rect(mask_meta, mask_instance)
        rect_xml = (
            f'<a:srcRect l="{src_rect[0]}" t="{src_rect[1]}" r="{src_rect[2]}" b="{src_rect[3]}"/>'
            if src_rect is not None
            else ""
        )
        unit_attrs: list[str] = []
        mask_units = mask_meta.get("mask_units")
        content_units = mask_meta.get("mask_content_units")
        if isinstance(mask_units, str):
            unit_attrs.append(f'maskUnits="{mask_units}"')
        if isinstance(content_units, str):
            unit_attrs.append(f'maskContentUnits="{content_units}"')
        attrs = (" " + " ".join(unit_attrs)) if unit_attrs else ""

        xml_parts = ["<a:mask" + attrs + ">"]
        if rect_xml:
            xml_parts.append(rect_xml)
        xml_parts.append(geometry_xml)
        xml_parts.append("</a:mask>")
        return "\n".join(xml_parts)

    @staticmethod
    def _src_rect(mask_meta: dict, mask_instance: MaskInstance | None) -> Tuple[int, int, int, int] | None:
        """Return srcRect tuple in thousandth percentages if available."""

        bounds = _extract_rect(mask_meta.get("instance_bounds")) or _extract_rect(
            mask_meta.get("target_bounds")
        )
        element_bounds = _extract_rect(mask_meta.get("element_bbox"))
        if mask_instance and mask_instance.bounds is not None:
            bounds = mask_instance.bounds
        if bounds is None or element_bounds is None or element_bounds.width == 0 or element_bounds.height == 0:
            return None

        left = max(0.0, (bounds.x - element_bounds.x) / element_bounds.width)
        top = max(0.0, (bounds.y - element_bounds.y) / element_bounds.height)
        right = max(
            0.0,
            (element_bounds.x + element_bounds.width - (bounds.x + bounds.width)) / element_bounds.width,
        )
        bottom = max(
            0.0,
            (element_bounds.y + element_bounds.height - (bounds.y + bounds.height)) / element_bounds.height,
        )

        return (
            _to_thousandth_percent(left),
            _to_thousandth_percent(top),
            _to_thousandth_percent(right),
            _to_thousandth_percent(bottom),
        )

    # ------------------------------------------------------------------ #
    # Fallback attempts
    # ------------------------------------------------------------------ #

    def _attempt_native(
        self,
        mask_ref: MaskRef,
        mask_meta: dict,
        mask_instance: MaskInstance | None,
        geometry_xml: str | None,
    ) -> _MaskAttemptResult:
        diagnostics: list[str] = []
        if not geometry_xml:
            if mask_ref.mask_id:
                diagnostics.append(f"Mask {mask_ref.mask_id} missing native geometry.")
            else:
                diagnostics.append("Mask missing native geometry.")
            return _MaskAttemptResult(False, diagnostics=diagnostics)

        xml = self._build_vector_mask_fragment(mask_ref, geometry_xml, mask_meta, mask_instance)
        return _MaskAttemptResult(True, xml=xml, diagnostics=diagnostics)

    def _attempt_mimic(
        self,
        mask_ref: MaskRef,
        mask_meta: dict,
        mask_instance: MaskInstance | None,
        geometry_result,
    ) -> _MaskAttemptResult:
        diagnostics: list[str] = []
        if geometry_result is None:
            geometry_result = compute_mask_geometry(mask_ref)
            if geometry_result is not None:
                diagnostics.extend(geometry_result.diagnostics)

        if geometry_result is None or geometry_result.geometry is None:
            diagnostics.append(_format_message(mask_ref, "mimic fallback unavailable; geometry missing."))
            return _MaskAttemptResult(False, diagnostics=diagnostics)

        geometry_xml = geometry_result.geometry.xml
        mask_meta.setdefault("geometry_xml", geometry_xml)
        bounds = geometry_result.geometry.bounds
        mask_meta.setdefault("bounds_px", (bounds.x, bounds.y, bounds.width, bounds.height))
        diagnostics.append(_format_message(mask_ref, "mimic fallback emitted using custom geometry."))
        xml = self._build_vector_mask_fragment(mask_ref, geometry_xml, mask_meta, mask_instance)
        return _MaskAttemptResult(True, xml=xml, diagnostics=diagnostics)

    def _attempt_emf(
        self,
        mask_ref: MaskRef,
        mask_meta: dict,
        mask_instance: MaskInstance | None,
        geometry_result,
        *,
        forced: bool = False,
    ) -> _MaskAttemptResult:
        diagnostics: list[str] = []
        if geometry_result is None:
            geometry_result = compute_mask_geometry(mask_ref)
            if geometry_result is not None:
                diagnostics.extend(geometry_result.diagnostics)

        if geometry_result is None or geometry_result.geometry is None or not geometry_result.segments:
            diagnostics.append(_format_message(mask_ref, "EMF fallback unavailable; geometry missing."))
            return _MaskAttemptResult(False, diagnostics=diagnostics)

        bounds = geometry_result.geometry.bounds
        context = self._unit_converter.create_context(
            width=max(bounds.width, 1.0),
            height=max(bounds.height, 1.0),
        )
        style = PathStyle(fill=SolidPaint("FFFFFF"), fill_rule="nonzero", stroke=None)
        emf_result = self._emf_adapter.render(
            segments=geometry_result.segments,
            style=style,
            unit_converter=self._unit_converter,
            conversion_context=context,
            dpi=int(round(context.dpi)),
        )
        if emf_result is None or not emf_result.emf_bytes:
            diagnostics.append(_format_message(mask_ref, "EMF fallback generation failed."))
            return _MaskAttemptResult(False, diagnostics=diagnostics)

        bounds_tuple = mask_meta.get("bounds_px") or (bounds.x, bounds.y, bounds.width, bounds.height)
        target_bounds = _tuple_from_rect(mask_meta.get("target_bounds")) or bounds_tuple
        metadata = {
            "source": "mask",
            "forced": forced,
            "bounds_px": bounds_tuple,
        }

        handle = self._mask_store.register_emf_mask(
            mask_id=getattr(mask_ref, "mask_id", None),
            emf_bytes=emf_result.emf_bytes,
            mode="policy_emf" if forced else "emf",
            bounds_px=bounds_tuple,
            target_bounds=target_bounds,
            metadata=metadata,
        )
        if self._assets is not None:
            self._assets.add_mask_asset(
                relationship_id=handle.relationship_id,
                part_name=handle.part_name,
                content_type=handle.content_type,
                data=emf_result.emf_bytes,
            )
        self._trace_mask(
            "mask_asset_registered",
            metadata={
                "mode": "policy_emf" if forced else "emf",
                "relationship_id": handle.relationship_id,
                "part_name": handle.part_name,
            },
            subject=getattr(mask_ref, "mask_id", None),
        )

        xml = self._build_blip_mask_fragment(handle.relationship_id, mask_meta, mask_instance)
        diagnostics.append(_format_message(mask_ref, f"EMF fallback emitted as {handle.part_name}."))
        return _MaskAttemptResult(True, xml=xml, diagnostics=diagnostics)

    def _attempt_raster(
        self,
        mask_ref: MaskRef,
        mask_meta: dict,
        mask_instance: MaskInstance | None,
        geometry_result,
        *,
        forced: bool = False,
    ) -> _MaskAttemptResult:
        diagnostics: list[str] = []
        bounds_tuple = mask_meta.get("bounds_px")
        if bounds_tuple is None and geometry_result and geometry_result.geometry is not None:
            bounds = geometry_result.geometry.bounds
            bounds_tuple = (bounds.x, bounds.y, bounds.width, bounds.height)
            mask_meta.setdefault("bounds_px", bounds_tuple)

        width = int(round(max(1.0, (bounds_tuple[2] if bounds_tuple else 32.0))))
        height = int(round(max(1.0, (bounds_tuple[3] if bounds_tuple else 32.0))))

        raster = self._raster_adapter.generate_placeholder(
            width_px=width,
            height_px=height,
            metadata={
                "mask_id": getattr(mask_ref, "mask_id", None),
                "forced": forced,
            },
        )

        handle = self._mask_store.register_raster_mask(
            mask_id=getattr(mask_ref, "mask_id", None),
            image_bytes=raster.image_bytes,
            mode="policy_raster" if forced else "raster",
            image_format="png",
            bounds_px=bounds_tuple,
            target_bounds=_tuple_from_rect(mask_meta.get("target_bounds")),
            metadata=raster.metadata,
        )
        if self._assets is not None:
            self._assets.add_mask_asset(
                relationship_id=handle.relationship_id,
                part_name=handle.part_name,
                content_type=handle.content_type,
                data=raster.image_bytes,
            )
        self._trace_mask(
            "mask_asset_registered",
            metadata={
                "mode": "policy_raster" if forced else "raster",
                "relationship_id": handle.relationship_id,
                "part_name": handle.part_name,
            },
            subject=getattr(mask_ref, "mask_id", None),
        )

        xml = self._build_blip_mask_fragment(handle.relationship_id, mask_meta, mask_instance)
        diagnostics.append(_format_message(mask_ref, f"Raster fallback emitted as {handle.part_name}."))
        return _MaskAttemptResult(True, xml=xml, diagnostics=diagnostics)

    def _build_blip_mask_fragment(
        self,
        relationship_id: str,
        mask_meta: dict,
        mask_instance: MaskInstance | None,
    ) -> str:
        attrs: list[str] = []
        mask_units = mask_meta.get("mask_units")
        content_units = mask_meta.get("mask_content_units")
        if isinstance(mask_units, str):
            attrs.append(f'maskUnits="{mask_units}"')
        if isinstance(content_units, str):
            attrs.append(f'maskContentUnits="{content_units}"')
        attr_str = (" " + " ".join(attrs)) if attrs else ""

        src_rect = self._src_rect(mask_meta, mask_instance)
        src_rect_xml = (
            f'<a:srcRect l="{src_rect[0]}" t="{src_rect[1]}" r="{src_rect[2]}" b="{src_rect[3]}"/>'
            if src_rect
            else ""
        )

        xml_parts = [f"<a:mask{attr_str}>"]
        xml_parts.append(
            "<a:blipFill dpi=\"0\" rotWithShape=\"0\">"
            f'<a:blip r:embed="{relationship_id}" cstate="print"/>'
        )
        if src_rect_xml:
            xml_parts.append(src_rect_xml)
        xml_parts.append("<a:stretch><a:fillRect/></a:stretch>")
        xml_parts.append("</a:blipFill>")
        xml_parts.append("</a:mask>")
        return "\n".join(xml_parts)


def _extract_rect(value) -> Rect | None:
    if isinstance(value, Rect):
        return value
    return None


def _to_thousandth_percent(value: float) -> int:
    scaled = max(0.0, min(1.0, value))
    return int(round(scaled * 100000))


def _fallback_sequence(mask_meta: dict) -> Tuple[str, ...]:
    order = mask_meta.get("fallback_order")
    if not order and isinstance(mask_meta.get("policy"), dict):
        order = mask_meta["policy"].get("fallback_order")
    if isinstance(order, (list, tuple)):
        requested = [str(item).lower() for item in order]
    elif isinstance(order, str):
        requested = [token.strip().lower() for token in order.split(",") if token.strip()]
    else:
        requested = []

    canonical = ["native", "mimic", "emf", "raster"]
    if not requested:
        return tuple(canonical)

    merged: list[str] = []
    seen: set[str] = set()

    # Preserve canonical priority for requested entries.
    requested_set = {token for token in requested if token}
    for token in canonical:
        if token in requested_set and token not in seen:
            merged.append(token)
            seen.add(token)

    # Append any additional, unrecognised entries at the end.
    for token in requested:
        if token and token not in seen:
            merged.append(token)
            seen.add(token)

    return tuple(merged)


def _format_message(mask_ref: MaskRef, message: str) -> str:
    prefix = f"Mask {mask_ref.mask_id} " if getattr(mask_ref, "mask_id", None) else "Mask "
    return prefix + message


def _tuple_from_rect(value) -> Tuple[float, float, float, float] | None:
    if value is None:
        return None
    if isinstance(value, Rect):
        return (value.x, value.y, value.width, value.height)
    if isinstance(value, (tuple, list)) and len(value) == 4:
        return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    return None


__all__ = ["MaskWriter", "MaskRenderResult"]
