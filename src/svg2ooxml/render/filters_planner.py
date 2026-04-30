"""Planning and attribute parsing for SVG filter primitives."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from svg2ooxml.common.numpy_compat import require_numpy
from svg2ooxml.common.units.lengths import (
    parse_number_list,
    parse_number_or_percent,
    split_length_list,
)
from svg2ooxml.core.resvg.painting.paint import parse_color
from svg2ooxml.core.resvg.usvg_tree import FilterNode, FilterPrimitive
from svg2ooxml.filters.input_descriptors import paint_input_descriptors
from svg2ooxml.filters.utils.parsing import parse_length
from svg2ooxml.render import filters_region as _region
from svg2ooxml.render.filters_image import plan_image_primitive
from svg2ooxml.render.filters_model import (
    RESVG_SUPPORTED_PRIMITIVES,
    ComponentTransferFunction,
    ComponentTransferPlan,
    FilterPlan,
    FilterPrimitivePlan,
    UnsupportedPrimitiveError,
)

np = require_numpy("svg2ooxml.render requires NumPy; install the 'render' extra.")


def plan_filter(
    filter_node: FilterNode,
    *,
    options: Mapping[str, Any] | None = None,
) -> FilterPlan | None:
    """Return a filter plan or *None* when the filter must fall back."""

    try:
        return _plan_filter(filter_node, options=options)
    except UnsupportedPrimitiveError:
        return None


def _plan_filter(
    filter_node: FilterNode,
    *,
    options: Mapping[str, Any] | None = None,
) -> FilterPlan:
    available: set[str] = {"SourceGraphic", "SourceAlpha"}
    input_descriptors = _declared_input_descriptors(options)
    available.update(input_descriptors)
    plans: list[FilterPrimitivePlan] = []

    for primitive in filter_node.primitives:
        tag_lower = primitive.tag.lower()
        if tag_lower not in RESVG_SUPPORTED_PRIMITIVES:
            raise UnsupportedPrimitiveError(
                primitive.tag, "primitive not supported", primitive=primitive
            )

        color_mode = _region.resolve_color_mode(filter_node, primitive)
        attrs = primitive.attributes
        inputs: list[str | None] = []
        extra: dict[str, Any] = {}

        if tag_lower == "fegaussianblur":
            inputs.append(
                _normalise_input(
                    attrs.get("in"),
                    available,
                    primitive,
                    allow_default=True,
                    label="in",
                )
            )
            extra["std_deviation"] = _parse_std_deviation(attrs.get("stdDeviation"))
        elif tag_lower == "feoffset":
            inputs.append(
                _normalise_input(
                    attrs.get("in"),
                    available,
                    primitive,
                    allow_default=True,
                    label="in",
                )
            )
            extra["dx"] = _parse_number(attrs.get("dx"))
            extra["dy"] = _parse_number(attrs.get("dy"))
        elif tag_lower == "fecolormatrix":
            inputs.append(
                _normalise_input(
                    attrs.get("in"),
                    available,
                    primitive,
                    allow_default=True,
                    label="in",
                )
            )
            if attrs.get("type", "matrix") == "matrix":
                values = _parse_float_list(attrs.get("values"))
                if values and len(values) != 20:
                    raise UnsupportedPrimitiveError(
                        primitive.tag,
                        "color matrix requires 20 values",
                        primitive=primitive,
                    )
        elif tag_lower == "fecomponenttransfer":
            inputs.append(
                _normalise_input(
                    attrs.get("in"),
                    available,
                    primitive,
                    allow_default=True,
                    label="in",
                )
            )
            extra["functions"] = _parse_component_transfer_functions(primitive)
        elif tag_lower == "feflood":
            inputs = []
        elif tag_lower == "feimage":
            inputs = []
            extra["image"] = plan_image_primitive(
                primitive, options=options, error_cls=UnsupportedPrimitiveError
            )
        elif tag_lower == "fecomposite":
            inputs.append(
                _normalise_input(
                    attrs.get("in"),
                    available,
                    primitive,
                    allow_default=True,
                    label="in",
                )
            )
            inputs.append(
                _normalise_input(
                    attrs.get("in2"),
                    available,
                    primitive,
                    allow_default=False,
                    label="in2",
                )
            )
            operator = (attrs.get("operator") or "over").lower()
            if operator not in {"over", "in", "out", "atop", "xor", "arithmetic"}:
                raise UnsupportedPrimitiveError(
                    primitive.tag,
                    f"operator {operator!r} not supported",
                    primitive=primitive,
                )
            extra["operator"] = operator
            if operator == "arithmetic":
                extra["k1"] = _parse_number(attrs.get("k1"), 0.0)
                extra["k2"] = _parse_number(attrs.get("k2"), 0.0)
                extra["k3"] = _parse_number(attrs.get("k3"), 0.0)
                extra["k4"] = _parse_number(attrs.get("k4"), 0.0)
        elif tag_lower == "feblend":
            inputs.append(
                _normalise_input(
                    attrs.get("in"),
                    available,
                    primitive,
                    allow_default=True,
                    label="in",
                )
            )
            inputs.append(
                _normalise_input(
                    attrs.get("in2"),
                    available,
                    primitive,
                    allow_default=False,
                    label="in2",
                )
            )
            mode = (attrs.get("mode") or "normal").strip().lower()
            if mode not in {"normal", "multiply", "screen", "darken", "lighten"}:
                raise UnsupportedPrimitiveError(
                    primitive.tag,
                    f"blend mode {mode!r} not supported",
                    primitive=primitive,
                )
            extra["mode"] = mode
        elif tag_lower == "fedisplacementmap":
            inputs.append(
                _normalise_input(
                    attrs.get("in"),
                    available,
                    primitive,
                    allow_default=True,
                    label="in",
                )
            )
            inputs.append(
                _normalise_input(
                    attrs.get("in2"),
                    available,
                    primitive,
                    allow_default=False,
                    label="in2",
                )
            )
            x_channel = (attrs.get("xChannelSelector") or "A").strip().upper()
            y_channel = (attrs.get("yChannelSelector") or "A").strip().upper()
            if x_channel not in {"R", "G", "B", "A"} or y_channel not in {
                "R",
                "G",
                "B",
                "A",
            }:
                raise UnsupportedPrimitiveError(
                    primitive.tag,
                    "channel selectors must be one of R, G, B, A",
                    primitive=primitive,
                )
            scale = _parse_number(attrs.get("scale"), 0.0)
            extra["scale"] = scale
            extra["x_channel"] = x_channel
            extra["y_channel"] = y_channel
        elif tag_lower == "feturbulence":
            inputs = []
            extra.update(_parse_turbulence_params(primitive))
        elif tag_lower in {"fediffuselighting", "fespecularlighting"}:
            light = _parse_light(primitive)
            if light is None:
                raise UnsupportedPrimitiveError(
                    primitive.tag, "missing light definition", primitive=primitive
                )
            inputs.append(
                _normalise_input(
                    attrs.get("in"),
                    available,
                    primitive,
                    allow_default=True,
                    label="in",
                )
            )
            extra["light"] = light
            extra["surface_scale"] = _parse_number(attrs.get("surfaceScale"), 1.0)
            if tag_lower == "fediffuselighting":
                extra["constant"] = _parse_number(attrs.get("diffuseConstant"), 1.0)
            else:
                extra["constant"] = _parse_number(attrs.get("specularConstant"), 1.0)
                extra["exponent"] = max(
                    1.0, _parse_number(attrs.get("specularExponent"), 1.0)
                )
            extra["kernel_length"] = _parse_kernel_unit(attrs.get("kernelUnitLength"))
            extra["lighting_color"] = _parse_lighting_color(attrs, primitive.styles)
        elif tag_lower == "femerge":
            inputs = list(_collect_merge_inputs(primitive, available))
        elif tag_lower == "femorphology":
            inputs.append(
                _normalise_input(
                    attrs.get("in"),
                    available,
                    primitive,
                    allow_default=True,
                    label="in",
                )
            )
            operator = (attrs.get("operator") or "erode").strip().lower()
            if operator not in {"erode", "dilate"}:
                raise UnsupportedPrimitiveError(
                    primitive.tag,
                    f"operator {operator!r} not supported",
                    primitive=primitive,
                )
            rx, ry = _parse_radius(attrs.get("radius"))
            extra["operator"] = operator
            extra["radius_x"] = rx
            extra["radius_y"] = ry
        elif tag_lower == "fetile":
            inputs.append(
                _normalise_input(
                    attrs.get("in"),
                    available,
                    primitive,
                    allow_default=False,
                    label="in",
                )
            )
        else:  # pragma: no cover - defensive, should not happen with whitelist
            raise UnsupportedPrimitiveError(
                primitive.tag, "primitive handler missing", primitive=primitive
            )

        plan = FilterPrimitivePlan(
            primitive=primitive,
            tag=primitive.tag,
            inputs=tuple(inputs),
            result_name=attrs.get("result"),
            color_mode=color_mode,
            extra=extra,
        )
        plans.append(plan)

        if plan.result_name:
            available.add(plan.result_name)

    return FilterPlan(
        filter_node=filter_node,
        primitives=plans,
        input_descriptors=input_descriptors,
    )


def _declared_input_descriptors(
    options: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(options, Mapping):
        return {}
    raw_inputs = options.get("filter_inputs")
    return paint_input_descriptors(raw_inputs)


def _normalise_input(
    raw_value: str | None,
    available: Iterable[str],
    primitive: FilterPrimitive,
    *,
    allow_default: bool,
    label: str,
) -> str | None:
    if raw_value is None or not raw_value.strip():
        if allow_default:
            return None
        raise UnsupportedPrimitiveError(
            primitive.tag, f"missing required input '{label}'", primitive=primitive
        )
    name = raw_value.strip()
    if name not in available:
        raise UnsupportedPrimitiveError(
            primitive.tag, f"input '{name}' is not available", primitive=primitive
        )
    return name


def _collect_merge_inputs(
    primitive: FilterPrimitive, available: Iterable[str]
) -> tuple[str | None, ...]:
    inputs: list[str | None] = []
    for node in primitive.children:
        if node.tag.lower() != "femergenode":
            continue
        node_input = _normalise_input(
            node.attributes.get("in"), available, node, allow_default=False, label="in"
        )
        inputs.append(node_input)
    if not inputs:
        raise UnsupportedPrimitiveError(
            primitive.tag,
            "feMerge requires at least one feMergeNode",
            primitive=primitive,
        )
    return tuple(inputs)


def _parse_number(value: str | None, default: float = 0.0) -> float:
    return parse_number_or_percent(value, default)


def _parse_float_list(payload: str | None) -> list[float]:
    return parse_number_list(payload)


def _parse_std_deviation(value: str | None) -> tuple[float, float]:
    values = _parse_length_list(value)
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        values = [values[0], values[0]]
    return (abs(values[0]), abs(values[1]))


def _parse_length_list(value: str | None) -> list[float]:
    if not value:
        return []
    return [parse_length(token) for token in split_length_list(value)]


def _parse_radius(value: str | None) -> tuple[float, float]:
    values = _parse_float_list(value)
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        values = [values[0], values[0]]
    return (max(0.0, values[0]), max(0.0, values[1]))


def _parse_component_transfer_functions(
    primitive: FilterPrimitive,
) -> ComponentTransferPlan:
    defaults = {
        "r": ComponentTransferFunction("identity"),
        "g": ComponentTransferFunction("identity"),
        "b": ComponentTransferFunction("identity"),
        "a": ComponentTransferFunction("identity"),
    }
    for node in primitive.children:
        tag = node.tag.lower()
        if not tag.startswith("fefunc") or len(tag) < 7:
            continue
        channel = tag[-1]
        if channel not in defaults:
            continue
        func_type = (node.attributes.get("type") or "identity").strip().lower()
        if func_type == "identity":
            defaults[channel] = ComponentTransferFunction("identity")
            continue
        if func_type == "linear":
            slope = _parse_number(node.attributes.get("slope"), 1.0)
            intercept = _parse_number(node.attributes.get("intercept"), 0.0)
            if any(
                node.attributes.get(name)
                for name in ("amplitude", "exponent", "offset")
            ):
                raise UnsupportedPrimitiveError(
                    primitive.tag, "gamma parameters not supported", primitive=primitive
                )
            defaults[channel] = ComponentTransferFunction(
                "linear", slope=slope, intercept=intercept
            )
            continue
        if func_type == "table":
            values = _parse_float_list(
                node.attributes.get("tableValues") or node.attributes.get("values")
            )
            if not values:
                raise UnsupportedPrimitiveError(
                    primitive.tag, "table function requires values", primitive=primitive
                )
            defaults[channel] = ComponentTransferFunction(
                "table", values=np.array(values, dtype=np.float32)
            )
            continue
        raise UnsupportedPrimitiveError(
            primitive.tag,
            f"function type {func_type!r} not supported",
            primitive=primitive,
        )

    return ComponentTransferPlan(
        red=defaults["r"],
        green=defaults["g"],
        blue=defaults["b"],
        alpha=defaults["a"],
    )


def _parse_turbulence_params(primitive: FilterPrimitive) -> dict[str, Any]:
    attrs = primitive.attributes
    freq_values = _parse_float_list(attrs.get("baseFrequency"))
    if not freq_values:
        freq_x = freq_y = 0.0
    elif len(freq_values) == 1:
        freq_x = freq_y = freq_values[0]
    else:
        freq_x, freq_y = freq_values[:2]
    seed = _parse_number(attrs.get("seed"), 0.0)
    octaves = int(max(1, round(_parse_number(attrs.get("numOctaves"), 1.0))))
    stitch = (attrs.get("stitchTiles") or "noStitch").strip()
    turbulence_type = (attrs.get("type") or "turbulence").strip()
    if turbulence_type not in {"turbulence", "fractalNoise"}:
        turbulence_type = "turbulence"
    return {
        "freq_x": freq_x,
        "freq_y": freq_y,
        "octaves": octaves,
        "seed": seed,
        "stitch": stitch,
        "turbulence_type": turbulence_type,
    }


def _parse_kernel_unit(value: str | None) -> tuple[float, float]:
    values = _parse_float_list(value)
    if not values:
        return (1.0, 1.0)
    if len(values) == 1:
        return (values[0], values[0])
    return (values[0], values[1])


def _parse_lighting_color(
    attrs: Mapping[str, str], styles: Mapping[str, str]
) -> tuple[float, float, float]:
    candidate = attrs.get("lighting-color") or styles.get("lighting-color") or "#ffffff"
    color = parse_color(candidate, 1.0)
    if color is None:
        color = parse_color("#ffffff", 1.0)
    return (color.r, color.g, color.b)


def _parse_light(primitive: FilterPrimitive) -> dict[str, Any] | None:
    for child in primitive.children:
        tag = child.tag.lower()
        attrs = child.attributes
        if tag == "fedistantlight":
            azimuth = math.radians(_parse_number(attrs.get("azimuth"), 0.0))
            elevation = math.radians(_parse_number(attrs.get("elevation"), 0.0))
            direction = (
                math.cos(elevation) * math.cos(azimuth),
                math.cos(elevation) * math.sin(azimuth),
                math.sin(elevation),
            )
            return {"type": "distant", "direction": direction}
        if tag == "fepointlight":
            return {
                "type": "point",
                "x": _parse_number(attrs.get("x"), 0.0),
                "y": _parse_number(attrs.get("y"), 0.0),
                "z": _parse_number(attrs.get("z"), 0.0),
            }
        if tag == "fespotlight":
            limiting = attrs.get("limitingConeAngle")
            cone_angle = (
                None if limiting is None else math.radians(_parse_number(limiting, 0.0))
            )
            return {
                "type": "spot",
                "x": _parse_number(attrs.get("x"), 0.0),
                "y": _parse_number(attrs.get("y"), 0.0),
                "z": _parse_number(attrs.get("z"), 0.0),
                "points_at_x": _parse_number(attrs.get("pointsAtX"), 0.0),
                "points_at_y": _parse_number(attrs.get("pointsAtY"), 0.0),
                "points_at_z": _parse_number(attrs.get("pointsAtZ"), 0.0),
                "limiting_cone": cone_angle,
                "cone_exponent": _parse_number(attrs.get("specularExponent"), 1.0),
            }
    return None


__all__ = ["plan_filter"]
