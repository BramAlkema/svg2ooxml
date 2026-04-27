"""Marker metadata extraction and marker profile classification."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lxml import etree

from svg2ooxml.common.conversions.transforms import parse_numeric_list
from svg2ooxml.common.geometry.paths import parse_path_data
from svg2ooxml.common.style.css_values import parse_style_declarations
from svg2ooxml.core.traversal.markers import MarkerDefinition
from svg2ooxml.core.traversal.runtime import local_name as _local_name
from svg2ooxml.ir.geometry import BezierSegment, LineSegment


def apply_marker_metadata(converter, element: etree._Element, metadata: dict[str, Any]) -> None:
    if metadata is None:
        return

    markers: dict[str, str] = {}

    def record_marker(raw_value: str | None, key: str) -> None:
        if not raw_value:
            return
        marker_id = converter._normalize_href_reference(raw_value)
        if marker_id:
            markers[key] = marker_id

    record_marker(element.get("marker-start"), "start")
    record_marker(element.get("marker-mid"), "mid")
    record_marker(element.get("marker-end"), "end")

    style_attr = element.get("style")
    for name, value in parse_style_declarations(style_attr)[0].items():
        if name in {"marker-start", "marker-mid", "marker-end"}:
            record_marker(value, name.split("-")[-1])

    if markers:
        existing = metadata.setdefault("markers", {})
        for key, value in markers.items():
            existing.setdefault(key, value)
        profiles = _build_marker_profiles(converter, markers)
        if profiles:
            existing_profiles = metadata.setdefault("marker_profiles", {})
            if isinstance(existing_profiles, dict):
                for key, value in profiles.items():
                    existing_profiles.setdefault(key, value)
        usage_bucket = getattr(converter, "_marker_usage", None)
        if isinstance(usage_bucket, set):
            usage_bucket.update(markers.values())
        trace_stage = getattr(converter, "_trace_stage", None)
        if callable(trace_stage):
            trace_stage(
                "marker_detected",
                stage="marker",
                metadata={"markers": dict(markers), "marker_profiles": dict(profiles)},
            )


def _build_marker_profiles(converter, markers: Mapping[str, str]) -> dict[str, dict[str, str]]:
    services = getattr(converter, "_services", None)
    marker_service = getattr(services, "marker_service", None)
    if marker_service is None:
        return {}

    profiles: dict[str, dict[str, str]] = {}
    for position, marker_id in markers.items():
        definition = marker_service.get_definition(marker_id)
        profile = _profile_from_marker_definition(definition)
        if profile:
            profiles[position] = profile
    return profiles


def _profile_from_marker_definition(definition: MarkerDefinition | None) -> dict[str, str] | None:
    if definition is None:
        return None
    marker_type = _classify_marker_type(definition.element)
    if marker_type is None:
        return None
    size = _classify_marker_size(definition)
    return {"type": marker_type, "size": size, "source": "geometry"}


def _classify_marker_size(definition: MarkerDefinition) -> str:
    extent = max(float(definition.marker_width), float(definition.marker_height))
    if definition.viewbox is not None:
        extent = max(extent, float(definition.viewbox.width), float(definition.viewbox.height))
    if extent <= 2.0:
        return "sm"
    if extent >= 8.0:
        return "lg"
    return "med"


def _classify_marker_type(marker_element: etree._Element) -> str | None:
    candidates: list[tuple[int, str]] = []
    for node in marker_element.iter():
        tag = _local_name(node.tag)
        if tag in {"circle", "ellipse"}:
            return "oval"
        points = _extract_points_for_classification(node, tag)
        if len(points) < 3:
            continue
        if _looks_like_diamond(points):
            candidates.append((80, "diamond"))
            continue
        if _looks_like_arrow(points):
            candidates.append((70, "arrow"))
            continue
        if len(points) == 3:
            candidates.append((60, "triangle"))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _extract_points_for_classification(node: etree._Element, local_name: str) -> list[tuple[float, float]]:
    if local_name == "path":
        path_data = node.get("d")
        if not path_data:
            return []
        try:
            segments = parse_path_data(path_data)
        except Exception:
            return []
        points: list[tuple[float, float]] = []
        for segment in segments:
            if isinstance(segment, LineSegment):
                points.append((segment.start.x, segment.start.y))
                points.append((segment.end.x, segment.end.y))
            elif isinstance(segment, BezierSegment):
                # Endpoints are sufficient for coarse marker archetype detection.
                points.append((segment.start.x, segment.start.y))
                points.append((segment.end.x, segment.end.y))
        return _dedupe_points(points)
    if local_name in {"polygon", "polyline"}:
        points_attr = node.get("points") or ""
        values = parse_numeric_list(points_attr)
        if len(values) < 6:
            return []
        points = [(values[i], values[i + 1]) for i in range(0, len(values) - 1, 2)]
        return _dedupe_points(points)
    return []


def _dedupe_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    ordered: list[tuple[float, float]] = []
    seen: set[tuple[int, int]] = set()
    for x, y in points:
        key = (int(round(x * 1000)), int(round(y * 1000)))
        if key in seen:
            continue
        seen.add(key)
        ordered.append((x, y))
    return ordered


def _looks_like_diamond(points: list[tuple[float, float]]) -> bool:
    if len(points) != 4:
        return False
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    height = max_y - min_y
    if width <= 1e-6 or height <= 1e-6:
        return False
    mid_x = min_x + width * 0.5
    mid_y = min_y + height * 0.5
    tol_x = width * 0.2
    tol_y = height * 0.2

    def _near(value: float, target: float, tolerance: float) -> bool:
        return abs(value - target) <= tolerance

    has_left = any(_near(x, min_x, tol_x) and _near(y, mid_y, tol_y) for x, y in points)
    has_right = any(_near(x, max_x, tol_x) and _near(y, mid_y, tol_y) for x, y in points)
    has_top = any(_near(y, min_y, tol_y) and _near(x, mid_x, tol_x) for x, y in points)
    has_bottom = any(_near(y, max_y, tol_y) and _near(x, mid_x, tol_x) for x, y in points)
    return has_left and has_right and has_top and has_bottom


def _looks_like_arrow(points: list[tuple[float, float]]) -> bool:
    if len(points) < 4:
        return False
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    if width <= 1e-6 or height <= 1e-6:
        return False
    return _has_arrow_profile(xs) or _has_arrow_profile(ys)


def _has_arrow_profile(coords: list[float]) -> bool:
    min_coord = min(coords)
    max_coord = max(coords)
    span = max_coord - min_coord
    if span <= 1e-6:
        return False
    tip_tol = span * 0.1
    rear_tol = span * 0.2
    inner_min = min_coord + span * 0.2
    inner_max = min_coord + span * 0.8

    tip_low = sum(1 for coord in coords if abs(coord - min_coord) <= tip_tol)
    tip_high = sum(1 for coord in coords if abs(coord - max_coord) <= tip_tol)
    rear_low = sum(1 for coord in coords if abs(coord - min_coord) <= rear_tol)
    rear_high = sum(1 for coord in coords if abs(coord - max_coord) <= rear_tol)
    inner = sum(1 for coord in coords if inner_min < coord < inner_max)

    if tip_high == 1 and rear_low >= 2 and inner >= 1:
        return True
    if tip_low == 1 and rear_high >= 2 and inner >= 1:
        return True
    return False
