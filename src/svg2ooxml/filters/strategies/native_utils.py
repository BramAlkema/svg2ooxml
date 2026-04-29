"""Small helpers shared by native filter strategy modules."""

from __future__ import annotations

import math
from typing import Any

from lxml import etree

from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.common.units.lengths import parse_number
from svg2ooxml.filters.primitives.component_transfer import ComponentTransferFilter


def primitive_local_name(primitive: etree._Element) -> str:
    return local_name(getattr(primitive, "tag", None)).lower()


def component_transfer_alpha_scale(
    transfer_filter: ComponentTransferFilter,
    functions: list[Any],
) -> float | None:
    alpha_scale: float | None = None
    for function in functions:
        channel = getattr(function, "channel", "")
        if channel == "a":
            if getattr(function, "func_type", "") == "identity":
                continue
            params = getattr(function, "params", {}) or {}
            if getattr(function, "func_type", "") != "linear":
                return None
            intercept = parse_number(params.get("intercept", 0.0), math.nan)
            slope = parse_number(params.get("slope", 1.0), math.nan)
            if math.isnan(intercept) or math.isnan(slope):
                return None
            if abs(intercept) > 1e-6:
                return None
            alpha_scale = slope
            continue

        if not transfer_filter._is_identity_function(function):
            return None

    return alpha_scale


def aggregate_blip_color_transforms(
    transforms: list[dict[str, object]],
) -> list[dict[str, object]]:
    aggregated: list[dict[str, object]] = []
    seen_order: list[str] = []
    alpha_mod_fix = 1.0
    sat_mod = 1.0
    hue_off = 0
    passthrough: list[dict[str, object]] = []

    for transform in transforms:
        tag = transform.get("tag")
        if not isinstance(tag, str):
            continue
        if tag not in seen_order:
            seen_order.append(tag)
        if tag == "alphaModFix":
            amount = parse_number(transform.get("amt", 100000), math.nan)
            if math.isnan(amount):
                continue
            alpha_mod_fix *= amount / 100000.0
        elif tag == "satMod":
            value = parse_number(transform.get("val", 100000), math.nan)
            if math.isnan(value):
                continue
            sat_mod *= value / 100000.0
        elif tag == "hueOff":
            value = parse_number(transform.get("val", 0), math.nan)
            if math.isnan(value):
                continue
            hue_off += int(round(value))
        else:
            passthrough.append(dict(transform))

    for tag in seen_order:
        if tag == "alphaModFix":
            amt = max(0, min(int(round(alpha_mod_fix * 100000)), 200000))
            if amt != 100000:
                aggregated.append({"tag": "alphaModFix", "amt": amt})
        elif tag == "satMod":
            val = max(0, min(int(round(sat_mod * 100000)), 400000))
            if val != 100000:
                aggregated.append({"tag": "satMod", "val": val})
        elif tag == "hueOff":
            val = hue_off % 21600000
            if val:
                aggregated.append({"tag": "hueOff", "val": val})

    aggregated.extend(passthrough)
    return aggregated


def coerce_non_negative_float(value: object) -> float | None:
    if not isinstance(value, (int, float, str)):
        return None
    coerced = parse_number(value, math.nan)
    if math.isnan(coerced):
        return None
    if coerced < 0:
        return None
    return coerced


def parse_float_attr(value: str | None) -> float:
    return parse_number(value, 0.0)


def is_additive_composite(k1: float, k2: float, k3: float, k4: float) -> bool:
    tolerance = 1e-6
    return (
        abs(k1) <= tolerance
        and abs(k2 - 1.0) <= tolerance
        and abs(k3 - 1.0) <= tolerance
        and abs(k4) <= tolerance
    )
