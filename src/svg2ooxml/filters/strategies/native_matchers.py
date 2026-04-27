"""Pattern matchers for editable native DrawingML filter stacks."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.filters.primitives.merge import MergeFilter

from .native_utils import (
    is_additive_composite,
    parse_float_attr,
    primitive_local_name,
)


def match_flood_blur_merge_stack(
    element: etree._Element,
) -> tuple[etree._Element, etree._Element, list[str]] | None:
    """Detect feFlood -> feGaussianBlur -> feMerge glow pattern."""
    primitives = [child for child in element if hasattr(child, "tag")]
    if len(primitives) != 3:
        return None

    tags = [primitive_local_name(child) for child in primitives]
    if tags != ["feflood", "fegaussianblur", "femerge"]:
        return None

    flood_primitive, blur_primitive, merge_primitive = primitives
    merge_inputs = MergeFilter()._parse_params(merge_primitive).inputs
    if "SourceGraphic" not in merge_inputs:
        return None

    blur_result = (blur_primitive.get("result") or "").strip()
    if not blur_result:
        return None

    non_source_inputs = [
        token for token in merge_inputs if token not in {"SourceGraphic", "SourceAlpha"}
    ]
    if non_source_inputs != [blur_result]:
        return None

    blur_input = (blur_primitive.get("in") or "").strip()
    flood_result = (flood_primitive.get("result") or "").strip()
    if blur_input and (not flood_result or blur_input != flood_result):
        return None

    return flood_primitive, blur_primitive, merge_inputs


def match_shadow_stack(
    element: etree._Element,
) -> tuple[etree._Element, etree._Element, etree._Element, list[str]] | None:
    """Detect feOffset->feGaussianBlur->feFlood->feComposite->feMerge shadow pattern."""
    primitives = [child for child in element if hasattr(child, "tag")]
    if len(primitives) != 5:
        return None

    tags = [primitive_local_name(child) for child in primitives]
    if tags != ["feoffset", "fegaussianblur", "feflood", "fecomposite", "femerge"]:
        return None

    offset_primitive, blur_primitive, flood_primitive, composite_primitive, merge_primitive = primitives
    composite_operator = (composite_primitive.get("operator") or "over").strip().lower()
    if composite_operator != "in":
        return None

    offset_input = (offset_primitive.get("in") or "SourceAlpha").strip()
    if offset_input not in {"SourceAlpha", "SourceGraphic"}:
        return None

    offset_result = (offset_primitive.get("result") or "").strip()
    blur_input = (blur_primitive.get("in") or "").strip()
    if not offset_result or blur_input != offset_result:
        return None

    blur_result = (blur_primitive.get("result") or "").strip()
    flood_result = (flood_primitive.get("result") or "").strip()
    composite_input_1 = (composite_primitive.get("in") or "").strip()
    composite_input_2 = (composite_primitive.get("in2") or "").strip()
    if not blur_result or not flood_result:
        return None
    if composite_input_1 != flood_result or composite_input_2 != blur_result:
        return None

    composite_result = (composite_primitive.get("result") or "").strip()
    if not composite_result:
        return None

    merge_inputs = MergeFilter()._parse_params(merge_primitive).inputs
    if "SourceGraphic" not in merge_inputs:
        return None

    non_source_inputs = [
        token for token in merge_inputs if token not in {"SourceGraphic", "SourceAlpha"}
    ]
    if non_source_inputs != [composite_result]:
        return None

    return offset_primitive, blur_primitive, flood_primitive, merge_inputs


def match_lighting_composite_stack(
    element: etree._Element,
) -> tuple[etree._Element, etree._Element] | None:
    """Detect feDiffuseLighting/feSpecularLighting + feComposite(arithmetic) pattern."""
    primitives = [child for child in element if hasattr(child, "tag")]
    if len(primitives) != 2:
        return None

    lighting_primitive, composite_primitive = primitives
    lighting_tag = primitive_local_name(lighting_primitive)
    composite_tag = primitive_local_name(composite_primitive)
    if lighting_tag not in {"fediffuselighting", "fespecularlighting"}:
        return None
    if composite_tag != "fecomposite":
        return None

    operator = (composite_primitive.get("operator") or "over").strip().lower()
    if operator != "arithmetic":
        return None

    coefficients = (
        parse_float_attr(composite_primitive.get("k1")),
        parse_float_attr(composite_primitive.get("k2")),
        parse_float_attr(composite_primitive.get("k3")),
        parse_float_attr(composite_primitive.get("k4")),
    )
    if not is_additive_composite(*coefficients):
        return None

    lighting_result_name = (lighting_primitive.get("result") or "").strip()
    if not lighting_result_name:
        return None

    composite_in = (composite_primitive.get("in") or "").strip()
    composite_in2 = (composite_primitive.get("in2") or "").strip()
    inputs = {composite_in, composite_in2}
    if inputs != {lighting_result_name, "SourceGraphic"}:
        return None

    return lighting_primitive, composite_primitive


def match_color_transform_stack(
    element: etree._Element,
) -> list[etree._Element] | None:
    """Match a chain of feColorMatrix/feComponentTransfer primitives."""
    primitives = [child for child in element if hasattr(child, "tag")]
    if len(primitives) < 2:
        return None

    previous_result_name: str | None = None
    for index, primitive in enumerate(primitives):
        local_tag = primitive_local_name(primitive)
        if local_tag not in {"fecolormatrix", "fecomponenttransfer"}:
            return None

        input_name = (primitive.get("in") or "").strip()
        if index == 0:
            if input_name and input_name not in {"SourceGraphic", "SourceAlpha"}:
                return None
        elif input_name and input_name != previous_result_name:
            return None

        previous_result_name = (primitive.get("result") or "").strip() or previous_result_name

    return primitives
