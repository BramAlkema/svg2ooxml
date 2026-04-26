"""Filter rendering orchestrator for svg2ooxml."""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Iterable

from svg2ooxml.color.utils import color_to_hex
from svg2ooxml.common.conversions.angles import radians_to_ppt
from svg2ooxml.common.conversions.opacity import opacity_to_ppt, parse_opacity
from svg2ooxml.common.ooxml_relationships import is_safe_relationship_id
from svg2ooxml.common.units import px_to_emu
from svg2ooxml.common.units.scalars import EMU_PER_INCH
from svg2ooxml.drawingml.emf_adapter import EMFAdapter, PaletteResolver
from svg2ooxml.drawingml.raster_adapter import RasterAdapter

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.utils.dml import is_effect_container
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.services.filter_types import FilterEffectResult

_ALLOWED_BLIP_TAGS = frozenset({
    "alphaModFix",
    "alphaMod",
    "alphaOff",
    "satMod",
    "satOff",
    "hueOff",
    "lumMod",
    "lumOff",
    "tint",
    "shade",
})
_RESERVED_SLIDE_RELATIONSHIP_IDS = {"rId1"}

HOOK_PATTERN = re.compile(r"<!--\s*svg2ooxml:(?P<name>\w+)(?P<attrs>[^>]*)-->", re.IGNORECASE)
ATTR_PATTERN = re.compile(r"(\w+)=\"([^\"]*)\"")


class FilterRenderer:
    """Bridge between FilterRegistry outputs and IR effects."""

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        palette_resolver: PaletteResolver | None = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._emf_adapter = EMFAdapter(palette_resolver=palette_resolver)
        self._raster_adapter = RasterAdapter()
        self._reuse_counter = 0

    def set_palette_resolver(self, resolver: PaletteResolver | None) -> None:
        """Install a palette resolver used for EMF fallback rendering."""

        self._emf_adapter.set_palette_resolver(resolver)

    def render(
        self,
        filter_results: Iterable[FilterResult],
        *,
        context: FilterContext | None = None,
    ) -> list[FilterEffectResult]:
        outputs: list[FilterEffectResult] = []
        policy = self._policy_from_context(context)
        for result in filter_results:
            if not isinstance(result, FilterResult) or not result.is_success():
                continue

            drawingml = result.drawingml or ""
            metadata = dict(result.metadata or {})

            hook_name, attrs, remainder = self._extract_hook(drawingml)
            if hook_name:
                builder = self._hook_builders().get(hook_name)
                if builder:
                    try:
                        drawingml = builder(hook_name, attrs, remainder, result, context)
                    except Exception:  # pragma: no cover - defensive logging
                        self._logger.debug("Hook builder %s failed", hook_name, exc_info=True)
                        drawingml = remainder or ""
                else:
                    drawingml = remainder or ""
            elif drawingml and drawingml.strip().startswith("<!--") and drawingml.strip().endswith("-->"):
                # Comment-only fragments are placeholders from the primitive layer.
                # Drop them here so fallback assets can be materialized below.
                drawingml = ""

            fragment = drawingml.strip()
            if fragment and not fragment.startswith("<!--") and not is_effect_container(fragment):
                drawingml = f"<a:effectLst>{fragment}</a:effectLst>"

            if not drawingml and result.fallback == "emf":
                drawingml = self._placeholder_emf(metadata, result, policy=policy)
                strategy = "vector"
            elif not drawingml and result.fallback in {"bitmap", "raster"}:
                drawingml = self._placeholder_raster(metadata, result, policy=policy)
                strategy = "raster"
            else:
                strategy = self._strategy_from_policy(result, policy)

            effect = CustomEffect(drawingml=drawingml)
            outputs.append(
                FilterEffectResult(
                    effect=effect,
                    strategy=strategy,
                    metadata=metadata,
                    fallback=result.fallback,
                )
            )
        return outputs

    # ------------------------------------------------------------------
    # Hook builders
    # ------------------------------------------------------------------

    def _hook_builders(self):
        return {
            "flood": self._build_flood,
            "offset": self._build_offset,
            "merge": self._build_pass_through,
            "tile": self._build_pass_through,
            "composite": self._build_pass_through,
            "blend": self._build_pass_through,
            "componentTransfer": self._build_comment_only,
            "convolveMatrix": self._build_comment_only,
            "image": self._build_comment_only,
            "diffuseLighting": self._build_comment_only,
            "specularLighting": self._build_comment_only,
        }

    def _build_flood(self, name, attrs, remainder, result, context) -> str:
        color = color_to_hex(attrs.get("color"), default="000000")
        opacity = parse_opacity(attrs.get("opacity"), default=1.0)
        alpha = opacity_to_ppt(opacity)

        effectLst = a_elem("effectLst")
        solidFill = a_sub(effectLst, "solidFill")
        srgbClr = a_sub(solidFill, "srgbClr", val=color)
        a_sub(srgbClr, "alpha", val=alpha)
        return to_string(effectLst)

    def _build_offset(self, name, attrs, remainder, result, context) -> str:
        try:
            dx = float(attrs.get("dx", "0"))
            dy = float(attrs.get("dy", "0"))
        except ValueError:
            dx = dy = 0.0

        dx_emu = int(px_to_emu(dx))
        dy_emu = int(px_to_emu(dy))
        distance = int(math.hypot(dx_emu, dy_emu))

        effectLst = a_elem("effectLst")

        if distance == 0:
            # Add XML comment using lxml.etree.Comment
            from lxml import etree
            effectLst.append(etree.Comment(" offset: no displacement "))
            return to_string(effectLst)

        # PowerPoint angle (0 = right, counter-clockwise positive, units 60000 per degree)
        angle_rad = math.atan2(dy_emu, dx_emu)
        ppt_angle = radians_to_ppt(angle_rad % (2 * math.pi))

        distance = min(distance, EMU_PER_INCH)

        outerShdw = a_sub(effectLst, "outerShdw", blurRad="0", dist=distance, dir=ppt_angle, algn="ctr")
        srgbClr = a_sub(outerShdw, "srgbClr", val="000000")
        a_sub(srgbClr, "alpha", val="0")

        return to_string(effectLst)

    def _build_pass_through(self, name, attrs, remainder, result, context) -> str:
        if remainder:
            return remainder
        return self._build_comment(name, attrs)

    def _build_comment_only(self, name, attrs, remainder, result, context) -> str:
        return self._build_comment(name, attrs)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_hook(self, drawingml: str):
        match = HOOK_PATTERN.search(drawingml)
        if not match:
            return None, {}, drawingml
        prefix = drawingml[: match.start()]
        if prefix.strip():
            return None, {}, drawingml
        name = match.group("name")
        attr_block = match.group("attrs") or ""
        attrs = {m.group(1): m.group(2) for m in ATTR_PATTERN.finditer(attr_block)}
        remainder = drawingml[match.end():].strip()
        return name, attrs, remainder

    def _build_comment(self, name: str, attrs: dict[str, str]) -> str:
        if not attrs:
            return f"<!-- svg2ooxml:{name} -->"
        pairs = " ".join(f'{key}="{value}"' for key, value in attrs.items())
        return f"<!-- svg2ooxml:{name} {pairs} -->"

    def _strategy_from_policy(self, result: FilterResult, policy: dict[str, object] | None) -> str:
        if policy is None:
            return "native"
        prefer_vector = bool(policy.get("prefer_emf_blend_modes"))
        if prefer_vector and result.metadata.get("filter_type") in {"blend", "component_transfer"}:
            return "vector"
        return "native"

    def _placeholder_emf(
        self,
        metadata: dict[str, object],
        result: FilterResult,
        *,
        policy: dict[str, object] | None,
    ) -> str:
        try:
            asset = self._ensure_emf_asset(metadata, result)
        except Exception:  # pragma: no cover - defensive fallback
            self._logger.debug("EMF adapter failed; falling back to placeholder", exc_info=True)
            asset = None

        if not asset:
            assets = metadata.setdefault("fallback_assets", [])
            placeholder_id = self._allocate_reuse_id("rIdEmfReuse")
            placeholder_asset = {
                "type": "emf",
                "relationship_id": placeholder_id,
                "placeholder": True,
            }
            if isinstance(assets, list):
                assets.append(placeholder_asset)
            from lxml import etree
            effectLst = a_elem("effectLst")
            effectLst.append(etree.Comment(f' svg2ooxml:emf placeholder="" relationship="{placeholder_id}" '))
            blipFill = a_sub(effectLst, "blipFill", rotWithShape="0")
            blip = a_sub(blipFill, "blip")
            blip.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed", placeholder_id)
            self._apply_blip_enrichment(blip, metadata, policy)
            return to_string(effectLst)


        rel_id = asset.get("relationship_id")
        if not is_safe_relationship_id(
            rel_id,
            reserved_ids=_RESERVED_SLIDE_RELATIONSHIP_IDS,
        ):
            rel_id = self._allocate_reuse_id("rIdEmfReuse")
            asset["relationship_id"] = rel_id
        assert isinstance(rel_id, str)

        width_emu = asset.get("width_emu")
        height_emu = asset.get("height_emu")
        data_hex = asset.get("data_hex")
        if not data_hex:
            raw = asset.get("data")
            if isinstance(raw, (bytes, bytearray)):
                data_hex = bytes(raw).hex()
                asset["data_hex"] = data_hex

        from lxml import etree

        comment_parts = [f'relationship="{rel_id}"']
        if width_emu is not None:
            comment_parts.append(f'width="{int(width_emu)}"')
        if height_emu is not None:
            comment_parts.append(f'height="{int(height_emu)}"')
        comment = " ".join(comment_parts)

        effectLst = a_elem("effectLst")
        effectLst.append(etree.Comment(f' svg2ooxml:emf {comment} '))

        # Build blipFill with r:embed attribute
        blipFill = a_sub(effectLst, "blipFill", rotWithShape="0")
        blip = a_sub(blipFill, "blip")
        blip.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed", rel_id)
        self._apply_blip_enrichment(blip, metadata, policy)

        if data_hex:
            extLst = a_sub(blip, "extLst")
            ext = a_sub(extLst, "ext", uri="{28A0092B-C50C-407E-A947-70E740481C1C}")
            ext.text = data_hex

        return to_string(effectLst)

    def _placeholder_raster(
        self,
        metadata: dict[str, object],
        result: FilterResult,
        *,
        policy: dict[str, object] | None,
    ) -> str:
        from lxml import etree

        assets_list = metadata.get("fallback_assets")
        existing_asset: dict[str, object] | None = None
        if isinstance(assets_list, list):
            for asset in assets_list:
                if isinstance(asset, dict) and asset.get("type") == "raster":
                    existing_asset = asset
                    break

        if existing_asset is not None:
            rel_id = existing_asset.get("relationship_id")
            if not is_safe_relationship_id(
                rel_id,
                reserved_ids=_RESERVED_SLIDE_RELATIONSHIP_IDS,
            ):
                rel_id = self._allocate_reuse_id("rIdRasterReuse")
                existing_asset["relationship_id"] = rel_id
            assert isinstance(rel_id, str)
            width_px = existing_asset.get("width_px")
            height_px = existing_asset.get("height_px")
            data_hex = existing_asset.get("data_hex")
            if not data_hex:
                raw = existing_asset.get("data")
                if isinstance(raw, (bytes, bytearray)):
                    data_hex = bytes(raw).hex()
                    existing_asset["data_hex"] = data_hex

            # Build a:effectLst with lxml
            effectLst = a_elem("effectLst")

            # Build comment
            comment_parts = [f'relationship="{rel_id}"']
            if width_px is not None:
                comment_parts.append(f'width="{int(width_px)}"')
            if height_px is not None:
                comment_parts.append(f'height="{int(height_px)}"')
            comment = " ".join(comment_parts)
            effectLst.append(etree.Comment(f' svg2ooxml:raster {comment} '))

            # Build a:blipFill
            blipFill = a_sub(effectLst, "blipFill", rotWithShape="0")
            blip = a_sub(blipFill, "blip")
            blip.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed", rel_id)
            self._apply_blip_enrichment(blip, metadata, policy)

            if data_hex:
                extLst = a_sub(blip, "extLst")
                ext = a_sub(extLst, "ext", uri="{svg2ooxml:raster}")
                ext.text = data_hex

            return to_string(effectLst)

        placeholder_meta: dict[str, object] = {}
        for key in ("policy", "radius_effective", "alpha", "color", "radius_max"):
            if key in metadata:
                placeholder_meta[key] = metadata[key]

        raster = self._raster_adapter.generate_placeholder(metadata=placeholder_meta)
        assets = metadata.setdefault("fallback_assets", [])
        if isinstance(assets, list):
            assets.append(
                {
                    "type": "raster",
                    "relationship_id": raster.relationship_id,
                    "width_px": raster.width_px,
                    "height_px": raster.height_px,
                    "metadata": raster.metadata,
                    "data_hex": raster.image_bytes.hex(),
                }
            )
        data_hex = raster.image_bytes.hex()

        # Build a:effectLst with lxml
        effectLst = a_elem("effectLst")

        # Build comment
        comment_text = f' svg2ooxml:raster relationship="{raster.relationship_id}" size="{len(raster.image_bytes)}" '
        effectLst.append(etree.Comment(comment_text))

        # Build a:blipFill
        blipFill = a_sub(effectLst, "blipFill", rotWithShape="0")
        blip = a_sub(blipFill, "blip")
        blip.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed", raster.relationship_id)
        self._apply_blip_enrichment(blip, metadata, policy)

        extLst = a_sub(blip, "extLst")
        ext = a_sub(extLst, "ext", uri="{svg2ooxml:raster}")
        ext.text = data_hex

        return to_string(effectLst)

    def _ensure_emf_asset(self, metadata: dict[str, object], result: FilterResult) -> dict[str, object] | None:
        asset = self._active_emf_asset(metadata)
        if asset is not None:
            return asset

        filter_type = self._filter_type(metadata, result)
        try:
            source_meta = result.metadata if isinstance(result.metadata, dict) else metadata
            if isinstance(source_meta, dict):
                source_meta = dict(source_meta)
            else:
                source_meta = metadata if isinstance(metadata, dict) else {}
            emf = self._emf_adapter.render_filter(filter_type, source_meta)
        except Exception:
            self._logger.debug("Failed to render EMF for filter %s", filter_type, exc_info=True)
            return None

        asset = {
            "type": "emf",
            "relationship_id": emf.relationship_id,
            "width_emu": emf.width_emu,
            "height_emu": emf.height_emu,
            "metadata": emf.metadata,
            "data_hex": emf.emf_bytes.hex(),
        }
        assets = metadata.setdefault("fallback_assets", [])
        if isinstance(assets, list):
            assets.append(asset)
        emf_meta = metadata.setdefault("emf_asset", {})
        if isinstance(emf_meta, dict):
            emf_meta.setdefault("width_emu", emf.width_emu)
            emf_meta.setdefault("height_emu", emf.height_emu)
            emf_meta.setdefault("filter_type", emf.metadata.get("filter_type", filter_type))
        return asset

    def _active_emf_asset(self, metadata: dict[str, object]) -> dict[str, object] | None:
        assets_list = metadata.get("fallback_assets")
        if isinstance(assets_list, list):
            for asset in assets_list:
                if isinstance(asset, dict) and asset.get("type") == "emf":
                    return asset
        return None

    def _filter_type(self, metadata: dict[str, object], result: FilterResult) -> str:
        if isinstance(metadata, dict):
            token = metadata.get("filter_type")
            if isinstance(token, str) and token:
                return token
        meta = result.metadata if isinstance(result.metadata, dict) else {}
        token = meta.get("filter_type") if isinstance(meta, dict) else None
        if isinstance(token, str) and token:
            return token
        return "generic"

    def _allocate_reuse_id(self, prefix: str) -> str:
        self._reuse_counter += 1
        return f"{prefix}{self._reuse_counter}"

    def _policy_from_context(self, context: FilterContext | None) -> dict[str, object] | None:
        if context is None:
            return None
        options = getattr(context, "options", None)
        if isinstance(options, dict):
            policy_opts = options.get("policy")
            if isinstance(policy_opts, dict):
                filter_policy = policy_opts.get("filter")
                if isinstance(filter_policy, dict):
                    return {**policy_opts, **filter_policy}
                return policy_opts
        return None

    def _apply_blip_enrichment(
        self,
        blip,
        metadata: dict[str, object],
        policy: dict[str, object] | None,
    ) -> None:
        if not isinstance(policy, dict):
            return
        if not bool(policy.get("enable_blip_effect_enrichment", False)):
            return
        candidates = metadata.get("blip_color_transforms")
        if not isinstance(candidates, list):
            return

        applied = False
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            tag = candidate.get("tag")
            if not isinstance(tag, str) or tag not in _ALLOWED_BLIP_TAGS:
                continue
            attrs: dict[str, str] = {}
            for attr_name in ("val", "amt"):
                if attr_name not in candidate:
                    continue
                raw = candidate[attr_name]
                if isinstance(raw, (int, float)):
                    attrs[attr_name] = str(int(round(raw)))
                elif isinstance(raw, str) and raw.strip():
                    attrs[attr_name] = raw.strip()
            if not attrs:
                continue
            a_sub(blip, tag, **attrs)
            applied = True
        if applied:
            metadata["blip_effect_enrichment_applied"] = True


__all__ = ["FilterRenderer"]
