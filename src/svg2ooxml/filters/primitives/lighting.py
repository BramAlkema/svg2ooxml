"""Lighting filter primitives (feDiffuseLighting & feSpecularLighting)."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.common.conversions.opacity import opacity_to_ppt
# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import parse_number
from svg2ooxml.units.conversion import px_to_emu


@dataclass
class LightSource:
    kind: str
    params: dict[str, float]


def _parse_light_source(primitive: etree._Element) -> LightSource | None:
    for node in primitive:
        if not hasattr(node, "tag"):
            continue
        local = node.tag.split("}", 1)[-1] if "}" in node.tag else node.tag
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
        kernel_unit = _parse_kernel_unit(primitive.get("kernelUnitLength"))
        color = (primitive.get("lighting-color") or "#ffffff").strip()
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
        approximation_allowed = bool(policy_options.get("approximation_allowed", True))
        if approximation_allowed:
            drawingml = _approximate_lighting_glow(
                color=color,
                intensity=_clamp_intensity(diffuse_constant / 2.0, minimum=0.2),
                radius_px=max(surface_scale, 1.0),
            )
            metadata["native_support"] = True
            metadata["approximation"] = "glow"
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
        kernel_unit = _parse_kernel_unit(primitive.get("kernelUnitLength"))
        color = (primitive.get("lighting-color") or "#ffffff").strip()
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
        approximation_allowed = bool(policy_options.get("approximation_allowed", True))
        if approximation_allowed:
            intensity = _clamp_intensity(specular_constant * 0.7, minimum=0.25)
            radius_px = max(surface_scale, 1.0) * max(1.0, min(specular_exponent, 5.0))
            drawingml = _approximate_lighting_glow(
                color=color,
                intensity=intensity,
                radius_px=radius_px,
            )
            metadata["native_support"] = True
            metadata["approximation"] = "glow"
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
            warnings=["feSpecularLighting rendered via resvg rasterization"],
        )


def _parse_kernel_unit(value: str | None) -> tuple[float | None, float | None]:
    if not value:
        return (None, None)
    if " " in value:
        x_str, y_str = value.split(" ", 1)
    else:
        x_str = y_str = value
    return (
        parse_number(x_str) if x_str else None,
        parse_number(y_str) if y_str else None,
    )


def _approximate_lighting_glow(*, color: str, intensity: float, radius_px: float) -> str:
    token = color.strip().lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    if len(token) != 6:
        token = "FFFFFF"
    alpha = opacity_to_ppt(_clamp_intensity(intensity))
    radius_emu = int(px_to_emu(max(0.0, radius_px)))
    effectLst = a_elem("effectLst")
    glow_elem = a_sub(effectLst, "glow", rad=radius_emu)
    srgb = a_sub(glow_elem, "srgbClr", val=token.upper())
    a_sub(srgb, "alpha", val=alpha)
    return to_string(effectLst)


def _clamp_intensity(value: float, *, minimum: float = 0.1) -> float:
    return max(minimum, min(float(value), 1.0))


__all__ = ["DiffuseLightingFilter", "SpecularLightingFilter"]
