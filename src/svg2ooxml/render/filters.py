"""Filter planning and execution."""

from __future__ import annotations

import base64
import binascii
import math
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

try:  # pragma: no cover - optional dependency guard
    import skia
except ImportError:  # pragma: no cover
    skia = None

from svg2ooxml.core.resvg.painting.paint import parse_color
from svg2ooxml.core.resvg.usvg_tree import FilterNode, FilterPrimitive
from svg2ooxml.render.surface import Surface

_GAMMA = 2.4
_INV_GAMMA = 1.0 / _GAMMA
_EPSILON = 1e-6

REGISTERED_FILTER_PRIMITIVES = {
    "fegaussianblur",
    "feoffset",
    "feflood",
    "fecolormatrix",
    "fecomposite",
    "feblend",
    "femerge",
    "fecomponenttransfer",
    "femorphology",
    "fetile",
    "feimage",
    "fedisplacementmap",
    "feturbulence",
    "fediffuselighting",
    "fespecularlighting",
    "feconvolvematrix",
    "fedropshadow",
    "feglow",
}

RESVG_SUPPORTED_PRIMITIVES = {
    "fegaussianblur",
    "feoffset",
    "feflood",
    "fecolormatrix",
    "fecomposite",
    "feblend",
    "femerge",
    "fecomponenttransfer",
    "femorphology",
    "fetile",
    "feimage",
    "fedisplacementmap",
    "feturbulence",
    "fediffuselighting",
    "fespecularlighting",
}

# Primitives registered in the legacy FilterRegistry but not yet handled by the
# resvg pipeline. Callers can surface this list for telemetry or logging so we
# know which tags still fall back to EMF/raster rendering.
_ADDITIONAL_UNSUPPORTED = {
    "fedropshadow",
    "feglow",
}
UNSUPPORTED_FILTER_PRIMITIVES = tuple(
    sorted((REGISTERED_FILTER_PRIMITIVES - RESVG_SUPPORTED_PRIMITIVES) | _ADDITIONAL_UNSUPPORTED)
)


class UnsupportedPrimitiveError(RuntimeError):
    """Raised when a filter primitive cannot be handled by the resvg pipeline."""

    def __init__(self, tag: str, reason: str, *, primitive: FilterPrimitive | None = None) -> None:
        message = f"{tag}: {reason}"
        super().__init__(message)
        self.tag = tag
        self.reason = reason
        self.primitive = primitive


@dataclass(slots=True)
class PrimitiveUnitScale:
    """Represent unit scaling for a filter primitive in pixel space."""

    scale_x: float
    scale_y: float
    bbox_width: float
    bbox_height: float


@dataclass(slots=True)
class ComponentTransferFunction:
    """Normalised feComponentTransfer channel function."""

    func_type: str
    values: np.ndarray | None = None
    slope: float = 1.0
    intercept: float = 0.0


@dataclass(slots=True)
class ComponentTransferPlan:
    red: ComponentTransferFunction
    green: ComponentTransferFunction
    blue: ComponentTransferFunction
    alpha: ComponentTransferFunction


@dataclass(slots=True)
class FilterPrimitivePlan:
    primitive: FilterPrimitive
    tag: str
    inputs: Tuple[Optional[str], ...] = ()
    result_name: Optional[str] = None
    color_mode: str = "sRGB"
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FilterPlan:
    filter_node: FilterNode
    primitives: List[FilterPrimitivePlan]


def plan_filter(filter_node: FilterNode) -> Optional[FilterPlan]:
    """Return a filter plan or *None* when the filter must fall back."""

    try:
        return _plan_filter(filter_node)
    except UnsupportedPrimitiveError:
        return None


def _plan_filter(filter_node: FilterNode) -> FilterPlan:
    available: set[str] = {"SourceGraphic", "SourceAlpha"}
    plans: List[FilterPrimitivePlan] = []

    for primitive in filter_node.primitives:
        tag_lower = primitive.tag.lower()
        if tag_lower not in RESVG_SUPPORTED_PRIMITIVES:
            raise UnsupportedPrimitiveError(primitive.tag, "primitive not supported", primitive=primitive)

        color_mode = _resolve_color_mode(filter_node, primitive)
        attrs = primitive.attributes
        inputs: List[Optional[str]] = []
        extra: Dict[str, Any] = {}

        if tag_lower == "fegaussianblur":
            inputs.append(_normalise_input(attrs.get("in"), available, primitive, allow_default=True, label="in"))
            extra["std_deviation"] = _parse_std_deviation(attrs.get("stdDeviation"))
        elif tag_lower == "feoffset":
            inputs.append(_normalise_input(attrs.get("in"), available, primitive, allow_default=True, label="in"))
            extra["dx"] = _parse_number(attrs.get("dx"))
            extra["dy"] = _parse_number(attrs.get("dy"))
        elif tag_lower == "fecolormatrix":
            inputs.append(_normalise_input(attrs.get("in"), available, primitive, allow_default=True, label="in"))
            if attrs.get("type", "matrix") == "matrix":
                values = _parse_float_list(attrs.get("values"))
                if values and len(values) != 20:
                    raise UnsupportedPrimitiveError(primitive.tag, "color matrix requires 20 values", primitive=primitive)
        elif tag_lower == "fecomponenttransfer":
            inputs.append(_normalise_input(attrs.get("in"), available, primitive, allow_default=True, label="in"))
            extra["functions"] = _parse_component_transfer_functions(primitive)
        elif tag_lower == "feflood":
            inputs = []
        elif tag_lower == "feimage":
            inputs = []
            extra["image"] = _plan_image_primitive(primitive)
        elif tag_lower == "fecomposite":
            inputs.append(_normalise_input(attrs.get("in"), available, primitive, allow_default=True, label="in"))
            inputs.append(_normalise_input(attrs.get("in2"), available, primitive, allow_default=False, label="in2"))
            operator = (attrs.get("operator") or "over").lower()
            if operator not in {"over", "in", "out", "atop", "xor"}:
                raise UnsupportedPrimitiveError(primitive.tag, f"operator {operator!r} not supported", primitive=primitive)
            extra["operator"] = operator
        elif tag_lower == "feblend":
            inputs.append(_normalise_input(attrs.get("in"), available, primitive, allow_default=True, label="in"))
            inputs.append(_normalise_input(attrs.get("in2"), available, primitive, allow_default=False, label="in2"))
            mode = (attrs.get("mode") or "normal").strip().lower()
            if mode not in {"normal", "multiply", "screen", "darken", "lighten"}:
                raise UnsupportedPrimitiveError(primitive.tag, f"blend mode {mode!r} not supported", primitive=primitive)
            extra["mode"] = mode
        elif tag_lower == "fedisplacementmap":
            inputs.append(_normalise_input(attrs.get("in"), available, primitive, allow_default=True, label="in"))
            inputs.append(_normalise_input(attrs.get("in2"), available, primitive, allow_default=False, label="in2"))
            x_channel = (attrs.get("xChannelSelector") or "A").strip().upper()
            y_channel = (attrs.get("yChannelSelector") or "A").strip().upper()
            if x_channel not in {"R", "G", "B", "A"} or y_channel not in {"R", "G", "B", "A"}:
                raise UnsupportedPrimitiveError(
                    primitive.tag, "channel selectors must be one of R, G, B, A", primitive=primitive
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
                raise UnsupportedPrimitiveError(primitive.tag, "missing light definition", primitive=primitive)
            inputs.append(_normalise_input(attrs.get("in"), available, primitive, allow_default=True, label="in"))
            extra["light"] = light
            extra["surface_scale"] = _parse_number(attrs.get("surfaceScale"), 1.0)
            if tag_lower == "fediffuselighting":
                extra["constant"] = _parse_number(attrs.get("diffuseConstant"), 1.0)
            else:
                extra["constant"] = _parse_number(attrs.get("specularConstant"), 1.0)
                extra["exponent"] = max(1.0, _parse_number(attrs.get("specularExponent"), 1.0))
            extra["kernel_length"] = _parse_kernel_unit(attrs.get("kernelUnitLength"))
            extra["lighting_color"] = _parse_lighting_color(attrs, primitive.styles)
        elif tag_lower == "femerge":
            inputs = list(_collect_merge_inputs(primitive, available))
        elif tag_lower == "femorphology":
            inputs.append(_normalise_input(attrs.get("in"), available, primitive, allow_default=True, label="in"))
            operator = (attrs.get("operator") or "erode").strip().lower()
            if operator not in {"erode", "dilate"}:
                raise UnsupportedPrimitiveError(primitive.tag, f"operator {operator!r} not supported", primitive=primitive)
            rx, ry = _parse_radius(attrs.get("radius"))
            extra["operator"] = operator
            extra["radius_x"] = rx
            extra["radius_y"] = ry
        elif tag_lower == "fetile":
            inputs.append(_normalise_input(attrs.get("in"), available, primitive, allow_default=False, label="in"))
        else:  # pragma: no cover - defensive, should not happen with whitelist
            raise UnsupportedPrimitiveError(primitive.tag, "primitive handler missing", primitive=primitive)

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

    return FilterPlan(filter_node=filter_node, primitives=plans)


def _normalise_input(
    raw_value: Optional[str],
    available: Iterable[str],
    primitive: FilterPrimitive,
    *,
    allow_default: bool,
    label: str,
) -> Optional[str]:
    if raw_value is None or not raw_value.strip():
        if allow_default:
            return None
        raise UnsupportedPrimitiveError(primitive.tag, f"missing required input '{label}'", primitive=primitive)
    name = raw_value.strip()
    if name not in available:
        raise UnsupportedPrimitiveError(primitive.tag, f"input '{name}' is not available", primitive=primitive)
    return name


def _collect_merge_inputs(primitive: FilterPrimitive, available: Iterable[str]) -> Tuple[Optional[str], ...]:
    inputs: List[Optional[str]] = []
    for node in primitive.children:
        if node.tag.lower() != "femergenode":
            continue
        node_input = _normalise_input(node.attributes.get("in"), available, node, allow_default=False, label="in")
        inputs.append(node_input)
    if not inputs:
        raise UnsupportedPrimitiveError(primitive.tag, "feMerge requires at least one feMergeNode", primitive=primitive)
    return tuple(inputs)


def _parse_number(value: Optional[str], default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        text = str(value).strip()
        if not text:
            return default
        if text.endswith("%"):
            return float(text[:-1]) / 100.0
        return float(text)
    except (TypeError, ValueError):
        return default


def _parse_float_list(payload: Optional[str]) -> List[float]:
    if not payload:
        return []
    values: List[float] = []
    for token in payload.replace(",", " ").split():
        try:
            values.append(float(token))
        except ValueError:
            continue
    return values


def _parse_std_deviation(value: Optional[str]) -> Tuple[float, float]:
    values = _parse_float_list(value)
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        values = [values[0], values[0]]
    return (abs(values[0]), abs(values[1]))


def _parse_radius(value: Optional[str]) -> Tuple[float, float]:
    values = _parse_float_list(value)
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        values = [values[0], values[0]]
    return (max(0.0, values[0]), max(0.0, values[1]))


def _parse_component_transfer_functions(primitive: FilterPrimitive) -> ComponentTransferPlan:
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
            if any(node.attributes.get(name) for name in ("amplitude", "exponent", "offset")):
                raise UnsupportedPrimitiveError(primitive.tag, "gamma parameters not supported", primitive=primitive)
            defaults[channel] = ComponentTransferFunction("linear", slope=slope, intercept=intercept)
            continue
        if func_type == "table":
            values = _parse_float_list(node.attributes.get("tableValues") or node.attributes.get("values"))
            if not values:
                raise UnsupportedPrimitiveError(primitive.tag, "table function requires values", primitive=primitive)
            defaults[channel] = ComponentTransferFunction("table", values=np.array(values, dtype=np.float32))
            continue
        raise UnsupportedPrimitiveError(primitive.tag, f"function type {func_type!r} not supported", primitive=primitive)

    return ComponentTransferPlan(
        red=defaults["r"],
        green=defaults["g"],
        blue=defaults["b"],
        alpha=defaults["a"],
    )


def _parse_turbulence_params(primitive: FilterPrimitive) -> Dict[str, Any]:
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


def _parse_kernel_unit(value: Optional[str]) -> tuple[float, float]:
    values = _parse_float_list(value)
    if not values:
        return (1.0, 1.0)
    if len(values) == 1:
        return (values[0], values[0])
    return (values[0], values[1])


def _parse_lighting_color(attrs: Mapping[str, str], styles: Mapping[str, str]) -> tuple[float, float, float]:
    candidate = attrs.get("lighting-color") or styles.get("lighting-color") or "#ffffff"
    color = parse_color(candidate, 1.0)
    if color is None:
        color = parse_color("#ffffff", 1.0)
    return (color.r, color.g, color.b)


def _parse_light(primitive: FilterPrimitive) -> Optional[Dict[str, Any]]:
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
            cone_angle = None if limiting is None else math.radians(_parse_number(limiting, 0.0))
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


def _plan_image_primitive(primitive: FilterPrimitive) -> Dict[str, Any]:
    href = _extract_href(primitive.attributes)
    if not href:
        raise UnsupportedPrimitiveError(primitive.tag, "feImage requires an href attribute", primitive=primitive)
    href = href.strip()
    try:
        mime, data = _decode_data_uri(href)
    except ValueError as exc:
        raise UnsupportedPrimitiveError(primitive.tag, str(exc), primitive=primitive) from exc

    if skia is None:
        raise UnsupportedPrimitiveError(primitive.tag, "skia is required to decode feImage data", primitive=primitive)
    image = skia.Image.MakeFromEncoded(data)
    if image is None:
        raise UnsupportedPrimitiveError(primitive.tag, "failed to decode feImage payload", primitive=primitive)
    try:
        pixels = image.tobytes()
    except Exception as exc:  # pragma: no cover - defensive
        raise UnsupportedPrimitiveError(primitive.tag, "unable to extract feImage pixels", primitive=primitive) from exc
    array = (
        np.frombuffer(pixels, dtype=np.uint8)
        .reshape(image.height(), image.width(), 4)
        .astype(np.float32)
        / 255.0
    )
    return {
        "surface": Surface(image.width(), image.height(), array),
        "mime": mime,
    }


def _extract_href(attrs: Mapping[str, str]) -> Optional[str]:
    for key in ("href", "xlink:href", "{http://www.w3.org/1999/xlink}href"):
        value = attrs.get(key)
        if value:
            return value
    return None


def _decode_data_uri(uri: str) -> Tuple[Optional[str], bytes]:
    if not uri.startswith("data:"):
        raise ValueError("external feImage references are not supported")
    header, _, payload = uri.partition(",")
    if not payload:
        raise ValueError("data URI is missing payload")
    meta = header[5:]  # strip "data:"
    is_base64 = ";base64" in meta
    if is_base64:
        try:
            data = base64.b64decode(payload, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("invalid base64 payload in data URI") from exc
    else:
        data = urllib.parse.unquote_to_bytes(payload)
    mime = None
    if meta:
        parts = [part for part in meta.split(";") if part]
        if parts:
            candidate = parts[0]
            if candidate != "base64":
                mime = candidate
    return mime, data


def apply_filter(
    surface: Surface,
    plan: FilterPlan,
    bounds: tuple[float, float, float, float],
    viewport: Any,
) -> Surface:
    region = _compute_filter_region(plan.filter_node, bounds, viewport)
    unit_scale = _primitive_unit_scale(plan.filter_node, bounds, viewport)

    images: Dict[str, Surface] = {
        "SourceGraphic": surface.clone(),
        "SourceAlpha": _extract_alpha(surface),
    }
    current = surface.clone()

    for primitive_plan in plan.primitives:
        primitive = primitive_plan.primitive
        tag_lower = primitive_plan.tag.lower()
        linear = primitive_plan.color_mode == "linearRGB"

        if tag_lower == "feflood":
            work_result = _apply_flood(
                surface.width,
                surface.height,
                primitive.attributes,
                primitive.styles,
                primitive_plan.color_mode,
            )
        elif tag_lower == "feturbulence":
            work_result = _apply_turbulence(
                surface.width,
                surface.height,
                primitive_plan.extra,
                unit_scale,
                linear,
            )
        elif tag_lower == "feimage":
            image_info = primitive_plan.extra.get("image")
            if image_info is None:
                raise UnsupportedPrimitiveError(primitive_plan.tag, "missing decoded image data", primitive=primitive)
            image_surface: Surface = image_info["surface"].clone()
            work_input = _convert_to_colorspace(image_surface, linear)
            work_result = _place_image_surface(work_input, surface.width, surface.height)
        else:
            inputs = _resolve_inputs(images, primitive_plan.inputs, current, linear)
            primary = inputs[0] if inputs else _convert_to_colorspace(current, linear)
            if tag_lower == "fegaussianblur":
                sigma_x, sigma_y = primitive_plan.extra.get("std_deviation", (0.0, 0.0))
                sigma_x *= unit_scale.scale_x
                sigma_y *= unit_scale.scale_y
                work_result = _apply_gaussian_blur(primary, sigma_x, sigma_y)
            elif tag_lower == "feoffset":
                dx = primitive_plan.extra.get("dx", 0.0) * unit_scale.scale_x
                dy = primitive_plan.extra.get("dy", 0.0) * unit_scale.scale_y
                work_result = _apply_offset(primary, dx, dy)
            elif tag_lower == "fecolormatrix":
                work_result = _apply_color_matrix(primary, primitive.attributes)
            elif tag_lower == "fecomposite":
                if len(inputs) < 2:
                    raise UnsupportedPrimitiveError(primitive_plan.tag, "feComposite requires two inputs", primitive=primitive)
                operator = primitive_plan.extra.get("operator", "over")
                work_result = _apply_composite(primary, inputs[1], operator)
            elif tag_lower == "feblend":
                if len(inputs) < 2:
                    raise UnsupportedPrimitiveError(primitive_plan.tag, "feBlend requires two inputs", primitive=primitive)
                mode = primitive_plan.extra.get("mode")
                work_result = _apply_blend(primary, inputs[1], mode, linear)
            elif tag_lower == "fediffuselighting":
                work_result = _apply_diffuse_lighting(
                    primary,
                    primitive_plan.extra,
                    unit_scale,
                )
            elif tag_lower == "fespecularlighting":
                work_result = _apply_specular_lighting(
                    primary,
                    primitive_plan.extra,
                    unit_scale,
                )
            elif tag_lower == "fedisplacementmap":
                if len(inputs) < 2:
                    raise UnsupportedPrimitiveError(
                        primitive_plan.tag, "feDisplacementMap requires two inputs", primitive=primitive
                    )
                work_result = _apply_displacement_map(
                    primary,
                    inputs[1],
                    primitive_plan.extra.get("scale", 0.0),
                    primitive_plan.extra.get("x_channel", "A"),
                    primitive_plan.extra.get("y_channel", "A"),
                    unit_scale,
                )
            elif tag_lower == "femerge":
                work_result = _apply_merge(inputs)
            elif tag_lower == "fecomponenttransfer":
                functions = primitive_plan.extra.get("functions")
                if not isinstance(functions, ComponentTransferPlan):
                    raise UnsupportedPrimitiveError(primitive_plan.tag, "component transfer plan missing", primitive=primitive)
                work_result = _apply_component_transfer(primary, functions)
            elif tag_lower == "femorphology":
                operator = primitive_plan.extra.get("operator", "erode")
                radius_x = primitive_plan.extra.get("radius_x", 0.0) * unit_scale.scale_x
                radius_y = primitive_plan.extra.get("radius_y", 0.0) * unit_scale.scale_y
                work_result = _apply_morphology(primary, operator, radius_x, radius_y)
            elif tag_lower == "fetile":
                work_result = primary.clone()
            else:  # pragma: no cover - defensive
                work_result = primary.clone()

        if linear:
            current = _linear_to_srgb_surface(work_result)
        else:
            current = work_result.clone()

        result_name = primitive_plan.result_name
        if result_name:
            images[result_name] = current.clone()
        images["_last"] = current.clone()

    _apply_filter_region(current, region, surface.width, surface.height)
    return current


def _resolve_inputs(
    images: Mapping[str, Surface],
    names: Sequence[Optional[str]],
    current: Surface,
    linear: bool,
) -> List[Surface]:
    resolved: List[Surface] = []
    for name in names:
        input_surface = _resolve_input_surface(images, name, current)
        resolved.append(_convert_to_colorspace(input_surface, linear))
    return resolved


def _apply_gaussian_blur(surface: Surface, sigma_x: float, sigma_y: float) -> Surface:
    if sigma_x <= 0.0 and sigma_y <= 0.0:
        return surface.clone()

    data = surface.data.copy()
    result = data

    if sigma_x > 0.0:
        kernel_x = _gaussian_kernel(sigma_x)
        pad_x = len(kernel_x) // 2
        temp = np.empty_like(result)
        for channel in range(result.shape[2]):
            channel_data = result[..., channel]
            padded = np.pad(channel_data, ((0, 0), (pad_x, pad_x)), mode="edge")
            temp[..., channel] = np.apply_along_axis(
                lambda row: np.convolve(row, kernel_x, mode="valid"),
                axis=1,
                arr=padded,
            )
        result = temp

    if sigma_y > 0.0:
        kernel_y = _gaussian_kernel(sigma_y)
        pad_y = len(kernel_y) // 2
        temp = np.empty_like(result)
        for channel in range(result.shape[2]):
            channel_data = result[..., channel]
            padded = np.pad(channel_data, ((pad_y, pad_y), (0, 0)), mode="edge")
            temp[..., channel] = np.apply_along_axis(
                lambda col: np.convolve(col, kernel_y, mode="valid"),
                axis=0,
                arr=padded,
            )
        result = temp

    return Surface(surface.width, surface.height, result)


def _gaussian_kernel(sigma: float) -> np.ndarray:
    sigma = max(float(sigma), _EPSILON)
    radius = max(int(3 * sigma + 0.5), 1)
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-(x**2) / (2.0 * sigma * sigma))
    kernel /= kernel.sum()
    return kernel.astype(np.float32)


def _apply_offset(surface: Surface, dx: float, dy: float) -> Surface:
    result = Surface.make(surface.width, surface.height)
    x_shift = int(round(dx))
    y_shift = int(round(dy))

    shifted = np.roll(surface.data, shift=(y_shift, x_shift), axis=(0, 1))
    if y_shift > 0:
        shifted[:y_shift, :, :] = 0.0
    elif y_shift < 0:
        shifted[y_shift:, :, :] = 0.0
    if x_shift > 0:
        shifted[:, :x_shift, :] = 0.0
    elif x_shift < 0:
        shifted[:, x_shift:, :] = 0.0

    result.data[...] = shifted
    return result


def _extract_alpha(surface: Surface) -> Surface:
    alpha_surface = Surface.make(surface.width, surface.height)
    alpha = surface.data[..., 3:4]
    alpha_surface.data[..., 3:4] = alpha
    return alpha_surface


def _apply_color_matrix(surface: Surface, attrs: Dict[str, str]) -> Surface:
    matrix_type = attrs.get("type", "matrix")
    data = surface.data.copy()

    if matrix_type == "saturate":
        value = float(attrs.get("values", "1") or 1.0)
        value = max(0.0, min(1.0, value))
        luminance = 0.2126 * data[..., 0] + 0.7152 * data[..., 1] + 0.0722 * data[..., 2]
        data[..., 0] = luminance * (1.0 - value) + data[..., 0] * value
        data[..., 1] = luminance * (1.0 - value) + data[..., 1] * value
        data[..., 2] = luminance * (1.0 - value) + data[..., 2] * value
        return Surface(surface.width, surface.height, data)

    if matrix_type == "luminanceToAlpha":
        luminance = 0.2126 * data[..., 0] + 0.7152 * data[..., 1] + 0.0722 * data[..., 2]
        result = Surface.make(surface.width, surface.height)
        result.data[..., 3] = luminance
        return result

    values = attrs.get("values", "")
    parts = [float(part) for part in values.replace(",", " ").split() if part]
    if len(parts) != 20:
        return surface.clone()
    matrix = np.array(parts, dtype=np.float32).reshape(4, 5)
    rgba = surface.data.reshape(-1, 4)
    transformed = np.dot(rgba, matrix[:, :4].T) + matrix[:, 4]
    transformed = transformed.reshape(surface.height, surface.width, 4)
    transformed = np.clip(transformed, 0.0, 1.0)
    return Surface(surface.width, surface.height, transformed.astype(np.float32))


def _apply_component_transfer(surface: Surface, plan: ComponentTransferPlan) -> Surface:
    data = surface.data.copy()
    alpha = np.clip(data[..., 3], 0.0, 1.0)
    safe_alpha = np.maximum(alpha, _EPSILON)

    unpremult = np.zeros_like(data[..., :3])
    mask = alpha > _EPSILON
    if np.any(mask):
        unpremult[mask] = data[..., :3][mask] / safe_alpha[mask, None]

    red = _apply_transfer_function(unpremult[..., 0], plan.red)
    green = _apply_transfer_function(unpremult[..., 1], plan.green)
    blue = _apply_transfer_function(unpremult[..., 2], plan.blue)
    out_alpha = np.clip(_apply_transfer_function(alpha, plan.alpha), 0.0, 1.0)

    out_rgb = np.stack([red, green, blue], axis=-1)
    out_rgb = np.clip(out_rgb, 0.0, 1.0)
    premult_rgb = out_rgb * out_alpha[..., None]

    result = Surface.make(surface.width, surface.height)
    result.data[..., :3] = premult_rgb.astype(np.float32)
    result.data[..., 3] = out_alpha.astype(np.float32)
    return result


def _apply_transfer_function(values: np.ndarray, func: ComponentTransferFunction) -> np.ndarray:
    if func.func_type == "identity" or func.func_type is None:
        return values.copy()
    if func.func_type == "linear":
        return np.clip(func.slope * values + func.intercept, 0.0, 1.0).astype(np.float32)
    if func.func_type == "table" and func.values is not None:
        table = np.clip(func.values, 0.0, 1.0).astype(np.float32)
        if table.size == 0:
            return values.copy()
        xp = np.linspace(0.0, 1.0, num=table.size, dtype=np.float32)
        flat = np.interp(np.clip(values, 0.0, 1.0).ravel(), xp, table)
        return flat.reshape(values.shape).astype(np.float32)
    return values.copy()


def _apply_morphology(surface: Surface, operator: str, radius_x: float, radius_y: float) -> Surface:
    rx = max(int(round(radius_x)), 0)
    ry = max(int(round(radius_y)), 0)
    if rx == 0 and ry == 0:
        return surface.clone()

    alpha = surface.data[..., 3]
    dilate = operator == "dilate"
    morphed_alpha = _morph_channel(alpha, rx, ry, dilate)
    morphed_alpha = np.clip(morphed_alpha, 0.0, 1.0)

    result = Surface.make(surface.width, surface.height)
    safe_alpha = np.maximum(surface.data[..., 3], _EPSILON)
    unpremult = np.zeros_like(surface.data[..., :3])
    mask = surface.data[..., 3] > _EPSILON
    if np.any(mask):
        unpremult[mask] = surface.data[..., :3][mask] / safe_alpha[mask, None]
    premult_rgb = np.clip(unpremult, 0.0, 1.0) * morphed_alpha[..., None]
    result.data[..., :3] = premult_rgb.astype(np.float32)
    result.data[..., 3] = morphed_alpha.astype(np.float32)
    return result


def _morph_channel(channel: np.ndarray, rx: int, ry: int, dilate: bool) -> np.ndarray:
    if rx == 0 and ry == 0:
        return channel.copy()
    padded = np.pad(channel, ((ry, ry), (rx, rx)), mode="edge")
    height, width = channel.shape
    result = np.empty_like(channel)
    for y in range(height):
        y0 = y
        y1 = y + 2 * ry + 1
        window = padded[y0:y1, :]
        for x in range(width):
            x0 = x
            x1 = x + 2 * rx + 1
            patch = window[:, x0:x1]
            result[y, x] = np.max(patch) if dilate else np.min(patch)
    return result


def _apply_merge(inputs: Sequence[Surface]) -> Surface:
    if not inputs:
        raise UnsupportedPrimitiveError("feMerge", "no merge inputs available")
    result = inputs[0].clone()
    for layer in inputs[1:]:
        result.blend(layer)
    return result


def _apply_turbulence(
    width: int,
    height: int,
    params: Mapping[str, Any],
    units: PrimitiveUnitScale,
    linear: bool,
) -> Surface:
    freq_x = abs(float(params.get("freq_x", 0.0)))
    freq_y = abs(float(params.get("freq_y", 0.0)))
    freq_x = max(freq_x, 1e-4)
    freq_y = max(freq_y, 1e-4)
    num_octaves = int(params.get("octaves", 1))
    num_octaves = max(1, min(num_octaves, 8))
    seed = int(params.get("seed", 0))
    turbulence_type = params.get("turbulence_type", "turbulence")
    stitch_tiles = str(params.get("stitch", "noStitch")).strip().lower() == "stitch"

    rng = np.random.default_rng(seed)
    if stitch_tiles:
        x = np.linspace(0.0, 1.0, num=max(width, 1), endpoint=False, dtype=np.float32)
        y = np.linspace(0.0, 1.0, num=max(height, 1), endpoint=False, dtype=np.float32)
    else:
        x = (np.arange(width, dtype=np.float32) + 0.5) / max(width, 1)
        y = (np.arange(height, dtype=np.float32) + 0.5) / max(height, 1)
    grid_x, grid_y = np.meshgrid(x, y)

    total = np.zeros((height, width), dtype=np.float32)
    amplitude = 1.0
    amplitude_total = 0.0

    base_freq_x = freq_x * max(units.bbox_width, 1.0)
    base_freq_y = freq_y * max(units.bbox_height, 1.0)

    for octave in range(num_octaves):
        phase = rng.uniform(0.0, 2.0 * math.pi, size=4)
        freq_mul = 2 ** octave
        fx = base_freq_x * freq_mul
        fy = base_freq_y * freq_mul
        if stitch_tiles:
            if width > 0:
                fx = round(fx * width) / max(width, 1)
            if height > 0:
                fy = round(fy * height) / max(height, 1)
        sample = (
            np.sin(2.0 * math.pi * fx * grid_x + phase[0])
            + np.sin(2.0 * math.pi * fy * grid_y + phase[1])
            + np.sin(2.0 * math.pi * fx * grid_y + phase[2])
            + np.sin(2.0 * math.pi * fy * grid_x + phase[3])
        )
        if turbulence_type == "turbulence":
            sample = np.abs(sample)
        total += sample * amplitude
        amplitude_total += amplitude
        amplitude *= 0.5

    total -= total.min()
    total /= total.max() + _EPSILON
    if stitch_tiles:
        total[:, -1] = total[:, 0]
        total[-1, :] = total[0, :]

    surface = Surface.make(width, height)
    if linear:
        surface.data[..., :3] = total[..., None]
    else:
        surface.data[..., :3] = total[..., None]
    surface.data[..., 3] = 1.0
    return surface


def _apply_diffuse_lighting(
    surface: Surface,
    params: Mapping[str, Any],
    units: PrimitiveUnitScale,
) -> Surface:
    light = params.get("light", {})
    color = np.array(params.get("lighting_color", (1.0, 1.0, 1.0)), dtype=np.float32)
    surface_scale = float(params.get("surface_scale", 1.0))
    diffuse_constant = float(params.get("constant", 1.0))
    kernel_length = params.get("kernel_length", (1.0, 1.0))

    height_map = _height_map_from_surface(surface) * surface_scale
    spacing_x = float(kernel_length[0]) if kernel_length else 1.0
    spacing_y = float(kernel_length[1]) if kernel_length else 1.0
    spacing_x = max(spacing_x, _EPSILON) * (units.scale_x or 1.0)
    spacing_y = max(spacing_y, _EPSILON) * (units.scale_y or 1.0)

    grad_y, grad_x = np.gradient(height_map, spacing_y, spacing_x, edge_order=1)
    normal = np.stack((-grad_x, -grad_y, np.ones_like(height_map)), axis=-1)
    norm = np.linalg.norm(normal, axis=-1, keepdims=True)
    normal = normal / np.maximum(norm, _EPSILON)

    light_vec, light_weight = _light_direction(light, surface.shape[1], surface.shape[0], units, height_map)
    dot = np.maximum(0.0, np.sum(normal * light_vec, axis=-1)) * light_weight

    intensity = diffuse_constant * dot
    rgb = np.clip(intensity[..., None] * color, 0.0, 1.0)
    alpha = np.clip(intensity, 0.0, 1.0)

    result = Surface.make(surface.width, surface.height)
    result.data[..., :3] = rgb * alpha[..., None]
    result.data[..., 3] = alpha
    return result


def _apply_specular_lighting(
    surface: Surface,
    params: Mapping[str, Any],
    units: PrimitiveUnitScale,
) -> Surface:
    light = params.get("light", {})
    light_type = params.get("light_type")
    color = np.array(params.get("lighting_color", (1.0, 1.0, 1.0)), dtype=np.float32)
    surface_scale = float(params.get("surface_scale", 1.0))
    specular_constant = float(params.get("constant", 1.0))
    specular_exponent = float(params.get("exponent", 1.0))
    kernel_length = params.get("kernel_length", (1.0, 1.0))

    height_map = _height_map_from_surface(surface) * surface_scale
    spacing_x = float(kernel_length[0]) if kernel_length else 1.0
    spacing_y = float(kernel_length[1]) if kernel_length else 1.0
    spacing_x = max(spacing_x, _EPSILON) * (units.scale_x or 1.0)
    spacing_y = max(spacing_y, _EPSILON) * (units.scale_y or 1.0)

    grad_y, grad_x = np.gradient(height_map, spacing_y, spacing_x, edge_order=1)
    normal = np.stack((-grad_x, -grad_y, np.ones_like(height_map)), axis=-1)
    norm = np.linalg.norm(normal, axis=-1, keepdims=True)
    normal = normal / np.maximum(norm, _EPSILON)

    light_vec, light_weight = _light_direction(light, surface.shape[1], surface.shape[0], units, height_map)
    view = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    view = view / np.linalg.norm(view)

    dot_nl = np.maximum(0.0, np.sum(normal * light_vec, axis=-1, keepdims=True))
    reflection = 2.0 * dot_nl * normal - light_vec
    reflection_norm = np.linalg.norm(reflection, axis=-1, keepdims=True)
    reflection = reflection / np.maximum(reflection_norm, _EPSILON)

    spec_amount = np.maximum(
        0.0, reflection[..., 0] * view[0] + reflection[..., 1] * view[1] + reflection[..., 2] * view[2]
    )
    intensity = specular_constant * np.power(spec_amount, specular_exponent)
    if light_type == "spot":
        intensity *= light_weight
    intensity *= light_weight
    intensity = np.clip(intensity, 0.0, 1.0)

    rgb = color * intensity[..., None]
    result = Surface.make(surface.width, surface.height)
    result.data[..., :3] = rgb
    result.data[..., 3] = intensity.astype(np.float32)
    result.data[..., :3] *= result.data[..., 3:4]
    return result


def _height_map_from_surface(surface: Surface) -> np.ndarray:
    alpha = np.clip(surface.data[..., 3], 0.0, 1.0)
    rgb = surface.data[..., :3]
    safe_alpha = np.maximum(alpha, _EPSILON)
    unpremult = np.zeros_like(rgb)
    mask = alpha > _EPSILON
    if np.any(mask):
        unpremult[mask] = rgb[mask] / safe_alpha[mask, None]
    luminance = (
        0.2126 * unpremult[..., 0]
        + 0.7152 * unpremult[..., 1]
        + 0.0722 * unpremult[..., 2]
    )
    # fall back to alpha when no colour is present
    height_map = np.where(mask, luminance, alpha)
    return np.clip(height_map, 0.0, 1.0).astype(np.float32)


def _light_direction(
    light: Mapping[str, Any],
    width: int,
    height: int,
    units: PrimitiveUnitScale,
    height_map: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if not light:
        direction = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        vec = np.broadcast_to(direction, (height, width, 3)).copy()
        weights = np.ones((height, width), dtype=np.float32)
        return vec, weights

    scale_x = units.scale_x if units.scale_x else 1.0
    scale_y = units.scale_y if units.scale_y else 1.0
    user_x = (np.arange(width, dtype=np.float32) + 0.5) / max(scale_x, _EPSILON)
    user_y = (np.arange(height, dtype=np.float32) + 0.5) / max(scale_y, _EPSILON)
    grid_x, grid_y = np.meshgrid(user_x, user_y)

    if light.get("type") == "distant":
        direction = np.array(light.get("direction", (0.0, 0.0, 1.0)), dtype=np.float32)
        norm = np.linalg.norm(direction)
        if norm <= _EPSILON:
            direction = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        else:
            direction = direction / norm
        vec = np.broadcast_to(direction, (height, width, 3)).copy()
        weight = np.ones((height, width), dtype=np.float32)
        return vec, weight

    light_pos = np.array(
        [
            float(light.get("x", 0.0)),
            float(light.get("y", 0.0)),
            float(light.get("z", 0.0)),
        ],
        dtype=np.float32,
    )
    surface_pos = np.stack([grid_x, grid_y, height_map], axis=-1)

    to_light = light_pos - surface_pos
    norm = np.linalg.norm(to_light, axis=-1, keepdims=True)
    direction = to_light / np.maximum(norm, _EPSILON)
    weight = np.ones((height, width), dtype=np.float32)

    if light.get("type") == "spot":
        axis = np.array(
            [
                float(light.get("points_at_x", 0.0)) - light_pos[0],
                float(light.get("points_at_y", 0.0)) - light_pos[1],
                float(light.get("points_at_z", 0.0)) - light_pos[2],
            ],
            dtype=np.float32,
        )
        axis_norm = np.linalg.norm(axis)
        if axis_norm <= _EPSILON:
            axis = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        else:
            axis = axis / axis_norm
        to_point = surface_pos - light_pos
        to_point_unit = to_point / np.maximum(np.linalg.norm(to_point, axis=-1, keepdims=True), _EPSILON)
        cos_angle = np.clip(np.sum(to_point_unit * axis, axis=-1), -1.0, 1.0)
        limiting = light.get("limiting_cone")
        if limiting is not None:
            mask = cos_angle >= math.cos(limiting)
            weight = np.where(mask, 1.0, 0.0)
        cone_exp = float(light.get("cone_exponent", 1.0))
        weight *= np.power(np.clip(cos_angle, 0.0, 1.0), cone_exp)

    return direction.astype(np.float32), weight.astype(np.float32)


def _apply_displacement_map(
    source: Surface,
    displacement: Surface,
    scale: float,
    x_channel: str,
    y_channel: str,
    units: PrimitiveUnitScale,
) -> Surface:
    if scale == 0.0:
        return source.clone()

    disp_data = displacement.data
    alpha = np.clip(disp_data[..., 3], 0.0, 1.0)
    denom = np.maximum(alpha, _EPSILON)[..., None]
    unpremult = np.where(alpha[..., None] > _EPSILON, disp_data[..., :3] / denom, 0.0)

    def _channel(value: str) -> np.ndarray:
        if value == "A":
            return alpha
        index = {"R": 0, "G": 1, "B": 2}.get(value, 0)
        return unpremult[..., index]

    x_values = _channel(x_channel)
    y_values = _channel(y_channel)

    scale_x = float(scale) * units.scale_x
    scale_y = float(scale) * units.scale_y

    dx = (x_values * 2.0 - 1.0) * scale_x
    dy = (y_values * 2.0 - 1.0) * scale_y

    height, width = source.height, source.width
    grid_x, grid_y = np.meshgrid(
        np.arange(width, dtype=np.float32),
        np.arange(height, dtype=np.float32),
    )
    sample_x = grid_x + dx.astype(np.float32)
    sample_y = grid_y + dy.astype(np.float32)

    sampled = _bilinear_sample(source.data, sample_x, sample_y)
    return Surface(width, height, sampled.astype(np.float32))


def _bilinear_sample(data: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    height, width = data.shape[:2]
    xs = np.clip(xs, 0.0, width - 1.0)
    ys = np.clip(ys, 0.0, height - 1.0)

    x0 = np.floor(xs).astype(np.int32)
    y0 = np.floor(ys).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)

    wx = (xs - x0).astype(np.float32)[..., None]
    wy = (ys - y0).astype(np.float32)[..., None]

    top_left = data[y0, x0]
    top_right = data[y0, x1]
    bottom_left = data[y1, x0]
    bottom_right = data[y1, x1]

    top = top_left * (1.0 - wx) + top_right * wx
    bottom = bottom_left * (1.0 - wx) + bottom_right * wx
    return top * (1.0 - wy) + bottom * wy


def _place_image_surface(image: Surface, width: int, height: int) -> Surface:
    result = Surface.make(width, height)
    w = min(width, image.width)
    h = min(height, image.height)
    result.data[:h, :w, :] = image.data[:h, :w, :]
    return result


def _apply_flood(width: int, height: int, attrs: Dict[str, str], styles: Dict[str, str], mode: str) -> Surface:
    color_value = attrs.get("flood-color") or styles.get("flood-color") or "#000000"
    opacity_value = attrs.get("flood-opacity") or styles.get("flood-opacity")
    opacity = float(opacity_value) if opacity_value is not None and opacity_value.strip() else 1.0
    color = parse_color(color_value, opacity)
    if color is None:
        color = parse_color("#000000", opacity)
    surface = Surface.make(width, height)
    rgb = np.array([color.r, color.g, color.b], dtype=np.float32)
    if mode == "linearRGB":
        rgb = np.power(np.clip(rgb, 0.0, 1.0), _GAMMA)
    premult = rgb * color.a
    rgba = np.concatenate([premult, np.array([color.a], dtype=np.float32)])
    surface.data[...] = rgba
    return surface


def _apply_composite(a: Surface, b: Surface, operator: str) -> Surface:
    result = Surface.make(a.width, a.height)
    src = a.data
    dst = b.data
    src_rgb = src[..., :3]
    src_alpha = src[..., 3:4]
    dst_rgb = dst[..., :3]
    dst_alpha = dst[..., 3:4]

    if operator == "over":
        out_alpha = src_alpha + dst_alpha * (1.0 - src_alpha)
        out_rgb = src_rgb + dst_rgb * (1.0 - src_alpha)
    elif operator == "in":
        out_rgb = src_rgb * dst_alpha
        out_alpha = src_alpha * dst_alpha
    elif operator == "out":
        out_rgb = src_rgb * (1.0 - dst_alpha)
        out_alpha = src_alpha * (1.0 - dst_alpha)
    elif operator == "atop":
        out_rgb = src_rgb * dst_alpha + dst_rgb * (1.0 - src_alpha)
        out_alpha = dst_alpha
    elif operator == "xor":
        out_rgb = src_rgb * (1.0 - dst_alpha) + dst_rgb * (1.0 - src_alpha)
        out_alpha = src_alpha * (1.0 - dst_alpha) + dst_alpha * (1.0 - src_alpha)
    else:
        out_rgb = src_rgb
        out_alpha = src_alpha

    result.data[..., :3] = out_rgb
    result.data[..., 3:4] = out_alpha
    return result


def _resolve_input_surface(images: Dict[str, Surface], name: Optional[str], fallback: Surface) -> Surface:
    if not name:
        return fallback.clone()
    surface = images.get(name)
    if surface is None:
        return fallback.clone()
    return surface.clone()


def _primitive_unit_scale(
    filter_node: FilterNode,
    bounds: tuple[float, float, float, float],
    viewport: Any,
) -> PrimitiveUnitScale:
    min_x, min_y, max_x, max_y = bounds
    bbox_width = max(max_x - min_x, 0.0)
    bbox_height = max(max_y - min_y, 0.0)
    if bbox_width == 0.0:
        bbox_width = viewport.width / viewport.scale_x
    if bbox_height == 0.0:
        bbox_height = viewport.height / viewport.scale_y

    units = (filter_node.primitive_units or "userSpaceOnUse").strip()
    if units == "objectBoundingBox":
        scale_x = bbox_width * viewport.scale_x
        scale_y = bbox_height * viewport.scale_y
    else:
        scale_x = viewport.scale_x
        scale_y = viewport.scale_y

    return PrimitiveUnitScale(scale_x=scale_x, scale_y=scale_y, bbox_width=bbox_width, bbox_height=bbox_height)


def _compute_filter_region(
    filter_node: FilterNode,
    bounds: tuple[float, float, float, float],
    viewport,
) -> tuple[int, int, int, int]:
    min_x, min_y, max_x, max_y = bounds
    bbox_width = max(max_x - min_x, 0.0)
    bbox_height = max(max_y - min_y, 0.0)
    viewport_width = viewport.width / viewport.scale_x
    viewport_height = viewport.height / viewport.scale_y
    if bbox_width == 0.0:
        bbox_width = viewport_width
    if bbox_height == 0.0:
        bbox_height = viewport_height

    attrs = filter_node.attributes
    units = (filter_node.filter_units or "objectBoundingBox").strip()

    if units == "objectBoundingBox":
        x_frac = _parse_fraction(attrs.get("x"), -0.1)
        y_frac = _parse_fraction(attrs.get("y"), -0.1)
        width_frac = _parse_fraction(attrs.get("width"), 1.2)
        height_frac = _parse_fraction(attrs.get("height"), 1.2)
        x = min_x + x_frac * bbox_width
        y = min_y + y_frac * bbox_height
        width = width_frac * bbox_width
        height = height_frac * bbox_height
    else:
        default_x = min_x - 0.1 * bbox_width
        default_y = min_y - 0.1 * bbox_height
        default_width = bbox_width * 1.2
        default_height = bbox_height * 1.2
        x = _parse_user_length(attrs.get("x"), default_x, viewport_width)
        y = _parse_user_length(attrs.get("y"), default_y, viewport_height)
        width = _parse_user_length(attrs.get("width"), default_width, viewport_width)
        height = _parse_user_length(attrs.get("height"), default_height, viewport_height)

    if width <= 0 or height <= 0:
        return (0, 0, viewport.width, viewport.height)

    left = int(math.floor((x - viewport.min_x) * viewport.scale_x))
    top = int(math.floor((y - viewport.min_y) * viewport.scale_y))
    right = int(math.ceil((x + width - viewport.min_x) * viewport.scale_x))
    bottom = int(math.ceil((y + height - viewport.min_y) * viewport.scale_y))

    left = max(0, min(viewport.width, left))
    right = max(left, min(viewport.width, right))
    top = max(0, min(viewport.height, top))
    bottom = max(top, min(viewport.height, bottom))
    return left, top, right, bottom


def _parse_fraction(value: Optional[str], default: float) -> float:
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        if value.endswith("%"):
            return float(value[:-1]) / 100.0
        return float(value)
    except ValueError:
        return default


def _parse_user_length(value: Optional[str], default: float, viewport_length: float) -> float:
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        if value.endswith("%"):
            pct = float(value[:-1])
            return (pct / 100.0) * viewport_length
        return float(value)
    except ValueError:
        return default


def _apply_filter_region(surface: Surface, region: tuple[int, int, int, int], width: int, height: int) -> None:
    x0, y0, x1, y1 = region
    mask = np.zeros((height, width), dtype=bool)
    mask[y0:y1, x0:x1] = True
    surface.data[~mask] = 0.0


def _resolve_color_mode(filter_node: FilterNode, primitive: FilterPrimitive) -> str:
    mode = primitive.attributes.get("color-interpolation-filters")
    if mode:
        return mode
    return filter_node.styles.get("color-interpolation-filters", "sRGB")


def _convert_to_colorspace(surface: Surface, linear: bool) -> Surface:
    if not linear:
        return surface.clone()
    result = surface.clone()
    rgb = np.clip(result.data[..., :3], 0.0, 1.0)
    result.data[..., :3] = np.power(rgb, _GAMMA)
    return result


def _linear_to_srgb_surface(surface: Surface) -> Surface:
    result = surface.clone()
    rgb = np.clip(result.data[..., :3], 0.0, 1.0)
    result.data[..., :3] = np.power(rgb, _INV_GAMMA)
    return result


def _apply_blend(a: Surface, b: Surface, mode: Optional[str], linear: bool) -> Surface:
    mode = (mode or "normal").strip().lower()
    _ = linear  # linear interpolation placeholder for future enhancements
    src = a.data.copy()
    dst = b.data.copy()

    src_rgb = src[..., :3]
    dst_rgb = dst[..., :3]
    src_alpha = np.clip(src[..., 3:4], 0.0, 1.0)
    dst_alpha = np.clip(dst[..., 3:4], 0.0, 1.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        src_un = np.where(src_alpha > 0, src_rgb / src_alpha, 0.0)
        dst_un = np.where(dst_alpha > 0, dst_rgb / dst_alpha, 0.0)

    if mode == "multiply":
        blend_un = src_un * dst_un
    elif mode == "screen":
        blend_un = src_un + dst_un - src_un * dst_un
    elif mode == "darken":
        blend_un = np.minimum(src_un, dst_un)
    elif mode == "lighten":
        blend_un = np.maximum(src_un, dst_un)
    else:
        blend_un = src_un

    blend_un = np.clip(blend_un, 0.0, 1.0)
    blend_rgb = blend_un * (src_alpha * dst_alpha)

    out_alpha = src_alpha + dst_alpha - src_alpha * dst_alpha
    out_rgb = blend_rgb + (1.0 - src_alpha) * dst_rgb + (1.0 - dst_alpha) * src_rgb
    out_rgb = np.clip(out_rgb, 0.0, 1.0)

    result = Surface.make(a.width, a.height)
    result.data[..., :3] = out_rgb
    result.data[..., 3:4] = np.clip(out_alpha, 0.0, 1.0)
    return result


__all__ = [
    "FilterPlan",
    "FilterPrimitivePlan",
    "UnsupportedPrimitiveError",
    "UNSUPPORTED_FILTER_PRIMITIVES",
    "plan_filter",
    "apply_filter",
]
