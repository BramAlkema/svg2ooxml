"""Numeric, list, and motion-path value parsing for SMIL animations."""

from __future__ import annotations

import re

from svg2ooxml.ir.animation import AnimationType

_NUMBER_LIST_SPLIT_RE = re.compile(r"[,\s]+")


# ------------------------------------------------------------------ #
# Module-level functions                                             #
# ------------------------------------------------------------------ #


def parse_animation_values(
    element,
    animation_type: AnimationType,
    *,
    target_attribute: str | None,
    namespace_map: dict[str, str],
    animation_summary,
    record_degradation,
    resolve_motion_path_reference,
    resolve_underlying_animation_value,
) -> list[str]:
    if animation_type == AnimationType.ANIMATE_MOTION:
        path = element.get("path")
        if path:
            return [path.strip()]
        mpath = (
            element.find(".//mpath")
            or element.find(".//svg:mpath", namespaces=namespace_map)
        )
        if mpath is not None:
            href = mpath.get("href", mpath.get("{http://www.w3.org/1999/xlink}href"))
            if href:
                resolved = resolve_motion_path_reference(element, href.strip())
                if resolved is not None:
                    return [resolved]
                animation_summary.add_warning(
                    f"animateMotion mpath reference unresolved: {href}"
                )
                record_degradation("mpath_reference_unresolved")
        # Fall back to from/to or values coordinate pairs
        values_attr = element.get("values")
        if values_attr:
            coords = [v.strip() for v in values_attr.split(";") if v.strip()]
            if coords:
                parts = [f"M {coords[0]}"] + [f"L {c}" for c in coords[1:]]
                return [" ".join(parts)]
        from_val = element.get("from")
        to_val = element.get("to")
        by_val = element.get("by")
        if from_val and to_val:
            return [f"M {from_val.strip()} L {to_val.strip()}"]
        if from_val and by_val:
            endpoint = combine_numeric_values(from_val, by_val, operator="+", record_degradation=record_degradation)
            return [
                f"M {from_val.strip()} L {(endpoint or by_val).strip()}"
            ]
        if to_val and by_val:
            startpoint = combine_numeric_values(to_val, by_val, operator="-", record_degradation=record_degradation)
            if startpoint:
                return [f"M {startpoint} L {to_val.strip()}"]
        if to_val:
            return [f"M 0,0 L {to_val.strip()}"]
        if by_val:
            return [f"M 0,0 L {by_val.strip()}"]
        return ["M 0,0"]

    values_attr = element.get("values")
    if values_attr:
        return [value.strip() for value in values_attr.split(";") if value.strip()]

    from_value = element.get("from")
    to_value = element.get("to")
    by_value = element.get("by")

    if from_value is not None and to_value is not None:
        return [from_value.strip(), to_value.strip()]

    if from_value is not None and by_value is not None:
        endpoint = combine_numeric_values(from_value, by_value, operator="+", record_degradation=record_degradation)
        return [from_value.strip(), endpoint or by_value.strip()]

    if to_value is not None and by_value is not None:
        startpoint = combine_numeric_values(to_value, by_value, operator="-", record_degradation=record_degradation)
        return [startpoint or by_value.strip(), to_value.strip()]

    if to_value is not None:
        underlying = resolve_underlying_animation_value(
            element,
            target_attribute=target_attribute,
        )
        if underlying is not None:
            return [underlying, to_value.strip()]
        return [to_value.strip()]

    if by_value is not None:
        return [by_value.strip()]

    if animation_type == AnimationType.SET:
        set_value = element.get("to")
        if set_value is not None:
            return [set_value.strip()]

    return []


def combine_numeric_values(
    left: str,
    right: str,
    *,
    operator: str,
    record_degradation,
) -> str | None:
    left_values = parse_numeric_list(left)
    right_values = parse_numeric_list(right)
    if left_values is None or right_values is None:
        record_degradation("by_value_non_numeric")
        return None
    if len(right_values) == 1 and len(left_values) > 1:
        right_values = right_values * len(left_values)
    if len(left_values) != len(right_values):
        record_degradation("by_value_dimension_mismatch")
        return None

    if operator == "+":
        combined = [
            left_value + right_value
            for left_value, right_value in zip(left_values, right_values, strict=True)
        ]
    elif operator == "-":
        combined = [
            left_value - right_value
            for left_value, right_value in zip(left_values, right_values, strict=True)
        ]
    else:
        return None
    return " ".join(format_number(value) for value in combined)


def parse_numeric_list(value: str) -> list[float] | None:
    tokens = [
        token
        for token in _NUMBER_LIST_SPLIT_RE.split(value.strip())
        if token
    ]
    if not tokens:
        return None
    try:
        return [float(token) for token in tokens]
    except ValueError:
        return None


def format_number(value: float) -> str:
    if abs(value) < 1e-12:
        return "0"
    return f"{value:.12g}"
