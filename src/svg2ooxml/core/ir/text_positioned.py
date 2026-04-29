"""Positioned SVG text helpers for :mod:`text_converter`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lxml import etree

from svg2ooxml.common.math_utils import coerce_positive_float
from svg2ooxml.core.ir.font_metrics import estimate_run_width as _estimate_run_width
from svg2ooxml.core.ir.text.font_metrics import scale_run_metrics
from svg2ooxml.core.ir.text.layout import (
    estimate_text_bbox,
    normalize_positioned_text,
    parse_text_length_list,
    text_scale_for_coord_space,
)
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.ir.geometry import Point
from svg2ooxml.ir.text import TextAnchor, TextFrame


class PositionedTextMixin:
    """Multi-position ``text``/``tspan`` conversion helpers."""

    def _needs_positioned_text(self, element: etree._Element) -> bool:
        for node in element.iter():
            tag = self._context.local_name(getattr(node, "tag", "")).lower()
            if tag == "tspan":
                if any(node.get(attr) for attr in ("x", "y", "dx", "dy")):
                    return True
                continue
            if tag != "text":
                continue
            if node.get("dx") or node.get("dy"):
                return True
            for attr in ("x", "y"):
                raw = node.get(attr)
                if raw and len(raw.replace(",", " ").split()) > 1:
                    return True
        return False

    def _convert_positioned_text(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
        base_style: Mapping[str, Any],
        run_metadata: Mapping[str, Any],
    ) -> list[TextFrame]:
        segments = self._collect_positioned_segments(element, base_style)
        if not segments:
            return []

        frames: list[TextFrame] = []
        font_service = self._context.services.resolve("font")
        policy_meta_accum: dict[str, Any] = {}
        decision = self._resolve_policy_decision()
        text_scale = text_scale_for_coord_space(coord_space)

        direction = base_style.get("direction") or element.get("direction") or None
        if isinstance(direction, str):
            direction = (
                direction.strip().lower()
                if direction.strip().lower() in {"rtl", "ltr"}
                else None
            )

        for text, style, x, y in segments:
            run = self._create_run_from_style(text, style)
            if not run.text:
                continue
            run = scale_run_metrics(run, text_scale)
            updated, run_policy = self.apply_policy(run)
            if run_policy:
                policy_meta_accum.update(run_policy)

            origin_x, origin_y = coord_space.apply_point(x, y)
            bbox = estimate_text_bbox(
                [updated], origin_x, origin_y, font_service=font_service
            )

            metadata: dict[str, Any] = dict(run_metadata)
            self._context.attach_policy_metadata(metadata, "text")
            if policy_meta_accum:
                policy_meta = metadata.setdefault("policy", {}).setdefault("text", {})
                policy_meta.update(policy_meta_accum)

            frame = TextFrame(
                origin=Point(origin_x, origin_y),
                anchor=TextAnchor.START,
                bbox=bbox,
                runs=[updated],
                baseline_shift=0.0,
                direction=direction,
                metadata=metadata,
            )
            if self._pipeline is not None:
                frame = self._pipeline.plan_frame(frame, [updated], decision)
            if self._smart_font_bridge is not None:
                frame = self._smart_font_bridge.enhance_frame(
                    frame, [updated], decision
                )

            self._context.trace_geometry_decision(element, "native", frame.metadata)
            frames.append(frame)

        return frames

    def _collect_positioned_segments(
        self,
        element: etree._Element,
        base_style: Mapping[str, Any],
    ) -> list[tuple[str, Mapping[str, Any], float, float]]:
        segments: list[tuple[str, Mapping[str, Any], float, float]] = []
        font_service = self._context.services.resolve("font")
        current_x = 0.0
        current_y = 0.0

        def apply_segment(
            text: str,
            style: Mapping[str, Any],
            x_values: list[float],
            y_values: list[float],
            dx_values: list[float],
            dy_values: list[float],
            *,
            preserve_space: bool,
        ) -> None:
            nonlocal current_x, current_y
            normalized = normalize_positioned_text(text, preserve_space)
            if not normalized:
                return

            run = self._create_run_from_style(normalized, style)
            per_char = (
                max(len(x_values), len(y_values), len(dx_values), len(dy_values)) > 1
            )

            if per_char:
                for idx, ch in enumerate(normalized):
                    if idx < len(x_values):
                        current_x = x_values[idx]
                    if idx < len(y_values):
                        current_y = y_values[idx]
                    if idx < len(dx_values):
                        current_x += dx_values[idx]
                    if idx < len(dy_values):
                        current_y += dy_values[idx]

                    if ch.strip():
                        segments.append((ch, style, current_x, current_y))
                    current_x += _estimate_run_width(ch, run, font_service)
                return

            if x_values:
                current_x = x_values[0]
            if y_values:
                current_y = y_values[0]
            if dx_values:
                current_x += dx_values[0]
            if dy_values:
                current_y += dy_values[0]

            if normalized.strip():
                segments.append((normalized, style, current_x, current_y))
            current_x += _estimate_run_width(normalized, run, font_service)

        def visit(
            node: etree._Element,
            style: Mapping[str, Any],
            preserve_space: bool,
        ) -> None:
            local = self._context.local_name(getattr(node, "tag", "")).lower()
            node_style = style
            if local == "tspan":
                node_style = self._context.style_resolver.compute_text_style(
                    node,
                    context=self._context.css_context,
                    parent_style=dict(style),
                )

            font_size_pt = coerce_positive_float(
                node_style.get("font_size_pt"),
                12.0,
            )
            x_values = parse_text_length_list(
                node.get("x"), font_size_pt, axis="x", context=self._context
            )
            y_values = parse_text_length_list(
                node.get("y"), font_size_pt, axis="y", context=self._context
            )
            dx_values = parse_text_length_list(
                node.get("dx"), font_size_pt, axis="x", context=self._context
            )
            dy_values = parse_text_length_list(
                node.get("dy"), font_size_pt, axis="y", context=self._context
            )

            xml_space = node.get("{http://www.w3.org/XML/1998/namespace}space")
            node_preserve = preserve_space or (xml_space == "preserve")
            if node.text:
                apply_segment(
                    node.text,
                    node_style,
                    x_values,
                    y_values,
                    dx_values,
                    dy_values,
                    preserve_space=node_preserve,
                )

            for child in node:
                visit(child, node_style, node_preserve)
                if child.tail:
                    apply_segment(
                        child.tail,
                        node_style,
                        [],
                        [],
                        [],
                        [],
                        preserve_space=node_preserve,
                    )

        visit(element, base_style, False)
        return segments
