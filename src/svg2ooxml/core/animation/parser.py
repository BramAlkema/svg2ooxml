from __future__ import annotations

"""SMIL animation parser that converts SVG elements into animation IR."""

from dataclasses import dataclass
import re
from typing import Iterable

from lxml import etree

from svg2ooxml.common.time import parse_time_value
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationSummary,
    AnimationTiming,
    AnimationType,
    CalcMode,
    FillMode,
    TransformType,
)


class SMILParsingError(Exception):
    """Raised when an animation element cannot be parsed."""


@dataclass(slots=True)
class ParsedAnimation:
    """Convenience wrapper for parser outputs."""

    definition: AnimationDefinition


class SMILParser:
    """Parse SMIL animation elements within an SVG DOM."""

    _ANIMATION_TAGS = (
        "animate",
        "animateTransform",
        "animateColor",
        "animateMotion",
        "set",
    )

    def __init__(self) -> None:
        self.animation_summary = AnimationSummary()
        self._namespace_map = {
            "svg": "http://www.w3.org/2000/svg",
            "smil": "http://www.w3.org/2001/SMIL20/",
            "xlink": "http://www.w3.org/1999/xlink",
        }

    # --------------------------------------------------------------------- #
    # Public API                                                            #
    # --------------------------------------------------------------------- #
    def parse_svg_animations(self, svg_element: etree._Element) -> list[AnimationDefinition]:
        animations: list[AnimationDefinition] = []
        animation_elements = self._find_animation_elements(svg_element)

        for element in animation_elements:
            try:
                definition = self._parse_animation_element(element)
            except SMILParsingError as exc:
                self.animation_summary.add_warning(f"Failed to parse animation: {exc}")
                continue
            except Exception:
                # Silently skip unexpected issues; callers can inspect warnings
                self.animation_summary.add_warning("Unexpected error parsing animation element")
                continue

            if definition:
                animations.append(definition)
                self._update_summary(definition)

        self._finalize_summary(animations)
        return animations

    def get_animation_summary(self) -> AnimationSummary:
        return self.animation_summary

    def reset_summary(self) -> None:
        self.animation_summary = AnimationSummary()

    def validate_animation_structure(self, animations: Iterable[AnimationDefinition]) -> list[str]:
        warnings: list[str] = []
        if not animations:
            warnings.append("No animations found")
            return warnings

        for animation in animations:
            if animation.timing.duration <= 0:
                warnings.append(f"Animation {animation.element_id} has non-positive duration")
        return warnings

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #
    def _find_animation_elements(self, svg_element: etree._Element) -> list[etree._Element]:
        elements: list[etree._Element] = []
        for tag in self._ANIMATION_TAGS:
            elements.extend(svg_element.xpath(f".//{tag}"))
            elements.extend(svg_element.xpath(f".//svg:{tag}", namespaces=self._namespace_map))
        return elements

    def _parse_animation_element(self, element: etree._Element) -> AnimationDefinition | None:
        tag_name = etree.QName(element).localname
        animation_type = self._get_animation_type(tag_name)
        if not animation_type:
            raise SMILParsingError(f"Unknown animation type: {tag_name}")

        element_id = self._get_target_element_id(element)
        if not element_id:
            raise SMILParsingError("Animation missing target element")

        if animation_type == AnimationType.ANIMATE_MOTION:
            target_attribute = "position"
        else:
            target_attribute = element.get("attributeName", "")
            if not target_attribute:
                raise SMILParsingError("Animation missing attributeName")

        values = self._parse_animation_values(element, animation_type)
        if not values:
            raise SMILParsingError("Animation missing values")

        timing = self._parse_timing(element)
        key_times = self._parse_key_times(element)
        key_splines = self._parse_key_splines(element)
        calc_mode = self._parse_calc_mode(element)
        transform_type = self._parse_transform_type(element, animation_type)

        additive = element.get("additive", "replace")
        accumulate = element.get("accumulate", "none")

        return AnimationDefinition(
            element_id=element_id,
            animation_type=animation_type,
            target_attribute=target_attribute,
            values=values,
            timing=timing,
            key_times=key_times,
            key_splines=key_splines,
            calc_mode=calc_mode,
            transform_type=transform_type,
            additive=additive,
            accumulate=accumulate,
        )

    def _get_animation_type(self, tag_name: str) -> AnimationType | None:
        mapping = {
            "animate": AnimationType.ANIMATE,
            "animateTransform": AnimationType.ANIMATE_TRANSFORM,
            "animateColor": AnimationType.ANIMATE_COLOR,
            "animateMotion": AnimationType.ANIMATE_MOTION,
            "set": AnimationType.SET,
        }
        return mapping.get(tag_name)

    def _get_target_element_id(self, element: etree._Element) -> str | None:
        href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
        if href and href.startswith("#"):
            return href[1:]

        parent = element.getparent()
        if parent is not None:
            parent_id = parent.get("id")
            if parent_id:
                return parent_id

        target = element.get("target")
        if target and target.startswith("#"):
            return target[1:]

        return None

    def _parse_animation_values(
        self,
        element: etree._Element,
        animation_type: AnimationType,
    ) -> list[str]:
        if animation_type == AnimationType.ANIMATE_MOTION:
            path = element.get("path")
            if path:
                return [path.strip()]
            mpath = element.find(".//mpath")
            if mpath is not None:
                href = mpath.get("href", mpath.get("{http://www.w3.org/1999/xlink}href"))
                if href:
                    return [href]
            return ["M 0,0"]

        values_attr = element.get("values")
        if values_attr:
            return [value.strip() for value in values_attr.split(";") if value.strip()]

        from_value = element.get("from")
        to_value = element.get("to")

        if from_value is not None and to_value is not None:
            return [from_value.strip(), to_value.strip()]

        if to_value is not None:
            return [to_value.strip()]

        if animation_type == AnimationType.SET:
            set_value = element.get("to")
            if set_value is not None:
                return [set_value.strip()]

        return []

    def _parse_timing(self, element: etree._Element) -> AnimationTiming:
        begin = parse_time_value(element.get("begin", "0s"))
        dur_value = element.get("dur", "1s")
        duration = float("inf") if dur_value == "indefinite" else parse_time_value(dur_value)

        repeat_attr = element.get("repeatCount", "1")
        if repeat_attr == "indefinite":
            repeat_count: int | str = "indefinite"
        else:
            try:
                repeat_count = int(float(repeat_attr))
            except (ValueError, TypeError):
                repeat_count = 1

        fill_attr = element.get("fill", "remove")
        fill_mode = FillMode.FREEZE if fill_attr == "freeze" else FillMode.REMOVE

        return AnimationTiming(
            begin=begin,
            duration=duration,
            repeat_count=repeat_count,
            fill_mode=fill_mode,
        )

    def _parse_key_times(self, element: etree._Element) -> list[float] | None:
        attr = element.get("keyTimes")
        if not attr:
            return None

        try:
            values = [float(value.strip()) for value in attr.split(";") if value.strip()]
        except (ValueError, TypeError):
            self.animation_summary.add_warning("Invalid keyTimes format")
            return None

        if not all(0.0 <= value <= 1.0 for value in values):
            self.animation_summary.add_warning("keyTimes values outside [0,1] range")
            return None

        return values or None

    def _parse_key_splines(self, element: etree._Element) -> list[list[float]] | None:
        attr = element.get("keySplines")
        if not attr:
            return None

        try:
            groups = [group.strip() for group in attr.split(";") if group.strip()]
            splines: list[list[float]] = []
            for group in groups:
                numbers = [float(value.strip()) for value in re.split(r"[,\s]+", group) if value.strip()]
                if len(numbers) != 4 or not all(0.0 <= number <= 1.0 for number in numbers):
                    raise ValueError
                splines.append(numbers)
        except (ValueError, TypeError):
            self.animation_summary.add_warning("Invalid keySplines format")
            return None

        return splines or None

    def _parse_calc_mode(self, element: etree._Element) -> CalcMode:
        attr = (element.get("calcMode") or "linear").lower()
        mapping = {
            "linear": CalcMode.LINEAR,
            "discrete": CalcMode.DISCRETE,
            "paced": CalcMode.PACED,
            "spline": CalcMode.SPLINE,
        }
        return mapping.get(attr, CalcMode.LINEAR)

    def _parse_transform_type(
        self,
        element: etree._Element,
        animation_type: AnimationType,
    ) -> TransformType | None:
        if animation_type != AnimationType.ANIMATE_TRANSFORM:
            return None

        attr = (element.get("type") or "").lower()
        mapping = {
            "translate": TransformType.TRANSLATE,
            "scale": TransformType.SCALE,
            "rotate": TransformType.ROTATE,
            "skewx": TransformType.SKEWX,
            "skewy": TransformType.SKEWY,
            "matrix": TransformType.MATRIX,
        }
        return mapping.get(attr)

    def _update_summary(self, animation: AnimationDefinition) -> None:
        if animation.timing.duration != float("inf"):
            end_time = animation.timing.get_end_time()
            if end_time != float("inf"):
                self.animation_summary.duration = max(self.animation_summary.duration, end_time)

        if animation.is_transform_animation():
            self.animation_summary.has_transforms = True
        if animation.is_motion_animation():
            self.animation_summary.has_motion_paths = True
        if animation.is_color_animation():
            self.animation_summary.has_color_animations = True
        if animation.key_splines:
            self.animation_summary.has_easing = True
        if animation.timing.begin > 0:
            self.animation_summary.has_sequences = True

    def _finalize_summary(self, animations: list[AnimationDefinition]) -> None:
        self.animation_summary.total_animations = len(animations)
        self.animation_summary.element_count = len({anim.element_id for anim in animations})
        self.animation_summary.calculate_complexity()


__all__ = ["SMILParser", "SMILParsingError", "ParsedAnimation"]
