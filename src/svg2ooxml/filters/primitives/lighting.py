"""Lighting filter primitives (feDiffuseLighting & feSpecularLighting)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from lxml import etree

from svg2ooxml.color.utils import color_to_hex, rgb_channels_to_hex
from svg2ooxml.common.conversions.angles import radians_to_ppt
from svg2ooxml.common.conversions.opacity import opacity_to_ppt
from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.common.units import px_to_emu

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import parse_number
from svg2ooxml.filters.utils.parsing import parse_length


@dataclass
class LightSource:
    kind: str
    params: dict[str, float]


def _parse_light_source(primitive: etree._Element) -> LightSource | None:
    for node in primitive:
        if not hasattr(node, "tag"):
            continue
        local = local_name(node.tag)
        if local == "feDistantLight":
            return LightSource(
                kind="distant",
                params={
                    "azimuth": parse_number(node.get("azimuth"), default=0.0),
                    "elevation": parse_number(node.get("elevation"), default=0.0),
                },
            )
        if local == "fePointLight":
            return LightSource(
                kind="point",
                params={
                    "x": parse_number(node.get("x")),
                    "y": parse_number(node.get("y")),
                    "z": parse_number(node.get("z")),
                },
            )
        if local == "feSpotLight":
            return LightSource(
                kind="spot",
                params={
                    "x": parse_number(node.get("x")),
                    "y": parse_number(node.get("y")),
                    "z": parse_number(node.get("z")),
                    "pointsAtX": parse_number(node.get("pointsAtX")),
                    "pointsAtY": parse_number(node.get("pointsAtY")),
                    "pointsAtZ": parse_number(node.get("pointsAtZ")),
                    "specularExponent": parse_number(node.get("specularExponent"), default=1.0),
                    "limitingConeAngle": parse_number(node.get("limitingConeAngle")),
                },
            )
    return None


class DiffuseLightingFilter(Filter):
    primitive_tags = ("feDiffuseLighting",)
    filter_type = "diffuse_lighting"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        surface_scale = parse_number(primitive.get("surfaceScale"), default=1.0)
        diffuse_constant = parse_number(primitive.get("diffuseConstant"), default=1.0)
        kernel_unit = _parse_kernel_unit(primitive.get("kernelUnitLength"), context)
        color = color_to_hex(primitive.get("lighting-color"), default="FFFFFF")
        light = _parse_light_source(primitive)
        metadata = {
            "filter_type": self.filter_type,
            "surface_scale": surface_scale,
            "diffuse_constant": diffuse_constant,
            "kernel_unit_length": kernel_unit,
            "lighting_color": color,
            "light": light.params if light else None,
            "light_type": light.kind if light else None,
            "native_support": False,
            "fallback_reason": "diffuse_lighting_requires_emf",
        }
        policy_options = context.policy
        approximation_allowed = bool(
            policy_options.get(
                "lighting_approximation_allowed",
                policy_options.get("approximation_allowed", True),
            )
        )
        if approximation_allowed and _source_is_svg_image(context):
            approximation_allowed = False
            metadata["approximation_blocked"] = "image_source"
        if approximation_allowed:
            drawingml, approximation_meta = _approximate_diffuse_lighting_effect(
                color=color,
                light=light,
                diffuse_constant=diffuse_constant,
                surface_scale=surface_scale,
            )
            metadata.update(approximation_meta)
            metadata["native_support"] = True
            metadata["no_op"] = False
            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback=None,
                metadata=metadata,
            )
        return FilterResult(
            success=True,
            drawingml="",
            fallback="raster",
            metadata=metadata,
            warnings=["feDiffuseLighting rendered via resvg rasterization"],
        )


class SpecularLightingFilter(Filter):
    primitive_tags = ("feSpecularLighting",)
    filter_type = "specular_lighting"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        surface_scale = parse_number(primitive.get("surfaceScale"), default=1.0)
        specular_constant = parse_number(primitive.get("specularConstant"), default=1.0)
        specular_exponent = parse_number(primitive.get("specularExponent"), default=1.0)
        kernel_unit = _parse_kernel_unit(primitive.get("kernelUnitLength"), context)
        color = color_to_hex(primitive.get("lighting-color"), default="FFFFFF")
        light = _parse_light_source(primitive)
        metadata = {
            "filter_type": self.filter_type,
            "surface_scale": surface_scale,
            "specular_constant": specular_constant,
            "specular_exponent": specular_exponent,
            "kernel_unit_length": kernel_unit,
            "lighting_color": color,
            "light": light.params if light else None,
            "light_type": light.kind if light else None,
            "native_support": False,
            "fallback_reason": "specular_lighting_rendered_via_resvg",
        }
        policy_options = context.policy
        approximation_allowed = bool(
            policy_options.get(
                "lighting_approximation_allowed",
                policy_options.get("approximation_allowed", True),
            )
        )
        if approximation_allowed and _source_is_svg_image(context):
            approximation_allowed = False
            metadata["approximation_blocked"] = "image_source"
        if approximation_allowed:
            drawingml, approximation_meta = _approximate_specular_lighting_effect(
                color=color,
                light=light,
                surface_scale=surface_scale,
                specular_constant=specular_constant,
                specular_exponent=specular_exponent,
            )
            metadata.update(approximation_meta)
            metadata["native_support"] = True
            metadata["no_op"] = False
            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback=None,
                metadata=metadata,
            )
        metadata.setdefault("approximation_blocked", "approximation_disabled")
        return FilterResult(
            success=True,
            drawingml="",
            fallback="raster",
            metadata=metadata,
            warnings=["feSpecularLighting rendered via resvg rasterization"],
        )


def _parse_kernel_unit(
    value: str | None,
    context: FilterContext,
) -> tuple[float | None, float | None]:
    if not value:
        return (None, None)
    parts = value.replace(",", " ").split()
    if len(parts) >= 2:
        x_str, y_str = parts[0], parts[1]
    else:
        x_str = y_str = value
    return (
        parse_length(x_str, context=context, axis="x") if x_str else None,
        parse_length(y_str, context=context, axis="y") if y_str else None,
    )


def _approximate_diffuse_lighting_effect(
    *,
    color: str,
    light: LightSource | None,
    diffuse_constant: float,
    surface_scale: float,
) -> tuple[str, dict[str, object]]:
    token = _normalise_color_token(color)
    overlay_token = _mix_toward_white(token, 0.68)
    overlay_alpha = _clamp_ratio(0.32 + diffuse_constant * 0.14, minimum=0.28, maximum=0.58)
    glow_alpha = _clamp_ratio(overlay_alpha * 0.34, minimum=0.10, maximum=0.22)
    inner_alpha = _clamp_ratio(0.04 + diffuse_constant * 0.05, minimum=0.04, maximum=0.16)
    glow_px = max(surface_scale * 0.7, 1.0)
    blur_px = max(surface_scale * 0.55, 0.8)
    soft_edge_px = max(surface_scale * 1.15, 1.25)
    distance_px = _lighting_distance_px(light, base=surface_scale * 0.5, maximum=3.0)
    direction = _lighting_direction_ppt(light)

    effectLst = a_elem("effectLst")
    fillOverlay = a_sub(effectLst, "fillOverlay", blend="screen")
    solidFill = a_sub(fillOverlay, "solidFill")
    overlayClr = a_sub(solidFill, "srgbClr", val=overlay_token)
    a_sub(overlayClr, "alpha", val=opacity_to_ppt(overlay_alpha))

    glow = a_sub(effectLst, "glow", rad=int(px_to_emu(glow_px)))
    glowClr = a_sub(glow, "srgbClr", val=overlay_token)
    a_sub(glowClr, "alpha", val=opacity_to_ppt(glow_alpha))

    inner = a_sub(
        effectLst,
        "innerShdw",
        blurRad=int(px_to_emu(blur_px)),
        dist=int(px_to_emu(distance_px)),
        dir=direction,
        algn="ctr",
        rotWithShape="0",
    )
    innerClr = a_sub(inner, "srgbClr", val=token)
    a_sub(innerClr, "alpha", val=opacity_to_ppt(inner_alpha))
    a_sub(effectLst, "softEdge", rad=int(px_to_emu(soft_edge_px)))

    return to_string(effectLst), {
        "approximation": "editable_lighting",
        "mimic_strategy": "fill_overlay_glow_inner_shadow_soft_edge",
        "overlay_alpha": overlay_alpha,
        "glow_alpha": glow_alpha,
        "glow_radius_px": glow_px,
        "inner_shadow_alpha": inner_alpha,
        "inner_shadow_blur_px": blur_px,
        "inner_shadow_distance_px": distance_px,
        "inner_shadow_direction": direction,
        "soft_edge_radius_px": soft_edge_px,
    }


def _approximate_specular_lighting_effect(
    *,
    color: str,
    light: LightSource | None,
    surface_scale: float,
    specular_constant: float,
    specular_exponent: float,
) -> tuple[str, dict[str, object]]:
    token = _normalise_color_token(color)
    overlay_token = _mix_toward_white(token, 0.48)
    exponent_weight = max(0.0, min(specular_exponent, 32.0)) / 32.0
    concentration = 1.0 - exponent_weight
    overlay_alpha = _clamp_ratio(
        0.03 + specular_constant * 0.05 + concentration * 0.03,
        minimum=0.03,
        maximum=0.12,
    )
    glow_alpha = _clamp_ratio(
        0.20 + specular_constant * 0.11 + exponent_weight * 0.17,
        minimum=0.20,
        maximum=0.46,
    )
    inner_alpha = _clamp_ratio(
        0.05 + specular_constant * 0.06 + exponent_weight * 0.08,
        minimum=0.05,
        maximum=0.22,
    )
    glow_px = max(surface_scale * (0.18 + concentration * 0.24), 0.45)
    blur_px = max(glow_px * 0.38, 0.3)
    distance_px = _lighting_distance_px(
        light,
        base=surface_scale * (0.14 + concentration * 0.08),
        maximum=1.8,
    )
    direction = _lighting_direction_ppt(light)

    effectLst = a_elem("effectLst")
    fillOverlay = a_sub(effectLst, "fillOverlay", blend="screen")
    solidFill = a_sub(fillOverlay, "solidFill")
    overlayClr = a_sub(solidFill, "srgbClr", val=overlay_token)
    a_sub(overlayClr, "alpha", val=opacity_to_ppt(overlay_alpha))

    glow = a_sub(effectLst, "glow", rad=int(px_to_emu(glow_px)))
    glowClr = a_sub(glow, "srgbClr", val=token)
    a_sub(glowClr, "alpha", val=opacity_to_ppt(glow_alpha))

    inner = a_sub(
        effectLst,
        "innerShdw",
        blurRad=int(px_to_emu(blur_px)),
        dist=int(px_to_emu(distance_px)),
        dir=direction,
        algn="ctr",
        rotWithShape="0",
    )
    innerClr = a_sub(inner, "srgbClr", val=token)
    a_sub(innerClr, "alpha", val=opacity_to_ppt(inner_alpha))

    return to_string(effectLst), {
        "approximation": "editable_lighting",
        "mimic_strategy": "fill_overlay_glow_inner_shadow",
        "overlay_alpha": overlay_alpha,
        "glow_alpha": glow_alpha,
        "glow_radius_px": glow_px,
        "inner_shadow_alpha": inner_alpha,
        "inner_shadow_blur_px": blur_px,
        "inner_shadow_distance_px": distance_px,
        "inner_shadow_direction": direction,
    }


def _normalise_color_token(value: str) -> str:
    token = value.strip().lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    if len(token) != 6:
        return "FFFFFF"
    return token.upper()


def _mix_toward_white(token: str, weight: float) -> str:
    weight = max(0.0, min(float(weight), 1.0))
    try:
        red = int(token[0:2], 16)
        green = int(token[2:4], 16)
        blue = int(token[4:6], 16)
    except ValueError:
        return token
    red = int(round(red + (255 - red) * weight))
    green = int(round(green + (255 - green) * weight))
    blue = int(round(blue + (255 - blue) * weight))
    return rgb_channels_to_hex(red, green, blue, scale="byte")


def _lighting_direction_ppt(light: LightSource | None) -> int:
    if light is None:
        return 0
    if light.kind == "distant":
        azimuth = math.radians(float(light.params.get("azimuth", 0.0)))
        elevation = math.radians(float(light.params.get("elevation", 0.0)))
        dx = math.cos(elevation) * math.cos(azimuth)
        dy = math.cos(elevation) * math.sin(azimuth)
    elif light.kind == "spot":
        dx = float(light.params.get("pointsAtX", 0.0)) - float(light.params.get("x", 0.0))
        dy = float(light.params.get("pointsAtY", 0.0)) - float(light.params.get("y", 0.0))
        if abs(dx) <= 1e-6 and abs(dy) <= 1e-6:
            dx = float(light.params.get("x", 0.0))
            dy = float(light.params.get("y", 0.0))
    else:
        dx = float(light.params.get("x", 0.0))
        dy = float(light.params.get("y", 0.0))

    if abs(dx) <= 1e-6 and abs(dy) <= 1e-6:
        return 0
    return radians_to_ppt(math.atan2(dy, dx) % (2 * math.pi))


def _lighting_distance_px(light: LightSource | None, *, base: float, maximum: float) -> float:
    if light is None:
        return 0.0
    strength = 0.75
    if light.kind == "distant":
        elevation = max(0.0, min(float(light.params.get("elevation", 45.0)), 89.0))
        strength = max(0.15, math.cos(math.radians(elevation)))
    return min(max(base, 0.0) * strength, maximum)


def _clamp_ratio(value: float, *, minimum: float = 0.1, maximum: float = 1.0) -> float:
    return max(minimum, min(float(value), maximum))


def _source_is_svg_image(context: FilterContext) -> bool:
    options = context.options if isinstance(context.options, dict) else {}
    element = options.get("element")
    tag = getattr(element, "tag", None)
    if isinstance(tag, str):
        if local_name(tag) == "image":
            return True

    filter_inputs = options.get("filter_inputs")
    if isinstance(filter_inputs, dict):
        source = filter_inputs.get("SourceGraphic")
        if isinstance(source, dict):
            shape_type = source.get("shape_type")
            if isinstance(shape_type, str) and shape_type.lower() == "image":
                return True
    return False


__all__ = ["DiffuseLightingFilter", "SpecularLightingFilter"]
