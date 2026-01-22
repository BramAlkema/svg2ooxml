"""Lighting filter primitives (feDiffuseLighting & feSpecularLighting)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import parse_number


@dataclass
class LightSource:
    kind: str
    params: Dict[str, float]


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
        return FilterResult(
            success=True,
            drawingml="",
            fallback="raster",
            metadata=metadata,
            warnings=["feSpecularLighting rendered via resvg rasterization"],
        )


def _parse_kernel_unit(value: str | None) -> Tuple[float | None, float | None]:
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


__all__ = ["DiffuseLightingFilter", "SpecularLightingFilter"]
