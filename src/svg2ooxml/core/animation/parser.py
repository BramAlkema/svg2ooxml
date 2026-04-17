"""SMIL animation parser that converts SVG elements into animation IR."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D, parse_transform_list
from svg2ooxml.common.time import parse_time_value
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationSummary,
    AnimationType,
    CalcMode,
    TransformType,
)

from . import timing_parser as _timing
from . import value_parser as _values


class SMILParsingError(Exception):
    """Raised when an animation element cannot be parsed."""


@dataclass(slots=True)
class ParsedAnimation:
    """Convenience wrapper for parser outputs."""

    definition: AnimationDefinition


def _parse_optional_duration_ms(value: str | None) -> int | None:
    """Parse an optional SMIL duration to milliseconds, or None."""
    if not value or value == "indefinite":
        return None
    try:
        return int(round(parse_time_value(value) * 1000))
    except (ValueError, TypeError):
        return None


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
        self._degradation_reasons: dict[str, int] = {}
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

        # Pre-assign IDs to target elements if they don't have one
        self._ensure_target_ids(animation_elements)

        for element in animation_elements:
            try:
                definition = self._parse_animation_element(element)
            except SMILParsingError as exc:
                self.animation_summary.add_warning(f"Failed to parse animation: {exc}")
                self._record_degradation("animation_parse_failed")
                continue
            except ValueError as exc:
                self.animation_summary.add_warning(f"Invalid animation definition: {exc}")
                self._record_degradation("animation_definition_invalid")
                continue
            except Exception:
                # Silently skip unexpected issues; callers can inspect warnings
                self.animation_summary.add_warning("Unexpected error parsing animation element")
                self._record_degradation("unexpected_parse_error")
                continue

            if definition:
                animations.append(definition)
                self._update_summary(definition)

        self._finalize_summary(animations)
        return animations

    def get_animation_summary(self) -> AnimationSummary:
        return self.animation_summary

    def get_degradation_reasons(self) -> dict[str, int]:
        """Return parser fallback/degradation reasons with occurrence counts."""
        return dict(self._degradation_reasons)

    def reset_summary(self) -> None:
        self.animation_summary = AnimationSummary()
        self._degradation_reasons = {}

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

        from_value = element.get("from")
        to_value = element.get("to")
        by_value = element.get("by")
        values = _values.parse_animation_values(
            element,
            animation_type,
            target_attribute=target_attribute,
            namespace_map=self._namespace_map,
            animation_summary=self.animation_summary,
            record_degradation=self._record_degradation,
            resolve_motion_path_reference=self._resolve_motion_path_reference,
            resolve_underlying_animation_value=self._resolve_underlying_animation_value,
        )
        if not values:
            raise SMILParsingError("Animation missing values")

        timing = _timing.parse_timing(
            element,
            animation_summary=self.animation_summary,
            record_degradation=self._record_degradation,
        )
        key_times = _timing.parse_key_times(
            element,
            animation_summary=self.animation_summary,
            record_degradation=self._record_degradation,
        )
        key_points = _timing.parse_key_points(
            element,
            animation_type,
            animation_summary=self.animation_summary,
            record_degradation=self._record_degradation,
        )
        key_splines = _timing.parse_key_splines(
            element,
            animation_summary=self.animation_summary,
            record_degradation=self._record_degradation,
        )
        calc_mode = _timing.parse_calc_mode(element, animation_type)
        key_times, key_points, key_splines = self._sanitize_interpolation_inputs(
            animation_type=animation_type,
            values=values,
            calc_mode=calc_mode,
            key_times=key_times,
            key_points=key_points,
            key_splines=key_splines,
        )
        transform_type = self._parse_transform_type(element, animation_type)
        motion_rotate = self._parse_motion_rotate(element, animation_type)
        motion_space_matrix = self._resolve_motion_space_matrix(
            element,
            animation_type=animation_type,
            target_attribute=target_attribute,
            transform_type=transform_type,
        )

        additive = element.get("additive", "replace")
        accumulate = element.get("accumulate", "none")
        restart = element.get("restart")  # "always", "whenNotActive", "never"

        # min/max duration constraints
        min_ms = _parse_optional_duration_ms(element.get("min"))
        max_ms = _parse_optional_duration_ms(element.get("max"))

        return AnimationDefinition(
            element_id=element_id,
            animation_type=animation_type,
            target_attribute=target_attribute,
            values=values,
            timing=timing,
            animation_id=element.get("id"),
            attribute_type=element.get("attributeType"),
            from_value=from_value.strip() if from_value is not None else None,
            to_value=to_value.strip() if to_value is not None else None,
            by_value=by_value.strip() if by_value is not None else None,
            key_times=key_times,
            key_points=key_points,
            key_splines=key_splines,
            calc_mode=calc_mode,
            transform_type=transform_type,
            additive=additive,
            accumulate=accumulate,
            motion_rotate=motion_rotate,
            motion_space_matrix=motion_space_matrix,
            restart=restart if restart in ("always", "whenNotActive", "never") else None,
            min_ms=min_ms,
            max_ms=max_ms,
            raw_attributes=self._extract_raw_attributes(element),
        )

    def _sanitize_interpolation_inputs(
        self,
        *,
        animation_type: AnimationType,
        values: list[str],
        calc_mode: CalcMode,
        key_times: list[float] | None,
        key_points: list[float] | None,
        key_splines: list[list[float]] | None,
    ) -> tuple[list[float] | None, list[float] | None, list[list[float]] | None]:
        """Normalize keyTimes/keySplines combinations to avoid hard parse drops."""
        is_motion_with_path = animation_type == AnimationType.ANIMATE_MOTION and len(values) == 1
        if key_times is not None:
            if is_motion_with_path:
                if len(key_times) < 2:
                    self.animation_summary.add_warning(
                        "Ignoring keyTimes for animateMotion: expected at least 2 entries"
                    )
                    self._record_degradation("motion_key_times_too_short")
                    key_times = None
            elif len(key_times) != len(values):
                self.animation_summary.add_warning(
                    f"keyTimes length mismatch: expected {len(values)}, got {len(key_times)}"
                )
                self._record_degradation("key_times_length_mismatch")
                key_times = None

        if key_points is not None:
            if animation_type != AnimationType.ANIMATE_MOTION:
                self.animation_summary.add_warning(
                    "Ignoring keyPoints because animation is not animateMotion"
                )
                self._record_degradation("key_points_non_motion")
                key_points = None
            elif key_times is not None and len(key_points) != len(key_times):
                self.animation_summary.add_warning(
                    f"keyPoints length mismatch: expected {len(key_times)}, got {len(key_points)}"
                )
                self._record_degradation("key_points_length_mismatch")
                key_points = None

        if key_splines is not None and calc_mode != CalcMode.SPLINE:
            self.animation_summary.add_warning(
                "Ignoring keySplines because calcMode is not spline"
            )
            self._record_degradation("key_splines_non_spline_mode")
            key_splines = None

        if (
            is_motion_with_path
            and key_splines is not None
            and key_times is None
            and len(key_splines) > 0
        ):
            # SVG stores animateMotion values as one path in this IR. For spline timing,
            # synthesize the SMIL segment clock so path keySplines are still retained.
            key_times = [
                index / len(key_splines)
                for index in range(len(key_splines) + 1)
            ]

        if key_splines is not None:
            if is_motion_with_path and key_times is not None:
                expected_splines = max(len(key_times) - 1, 0)
            else:
                expected_splines = max(len(values) - 1, 0)
            if len(key_splines) != expected_splines:
                self.animation_summary.add_warning(
                    f"keySplines length mismatch: expected {expected_splines}, got {len(key_splines)}"
                )
                self._record_degradation("key_splines_length_mismatch")
                key_splines = None

        if (
            calc_mode == CalcMode.SPLINE
            and key_splines
            and key_times is None
            and len(values) > 1
            and not is_motion_with_path
        ):
            # SMIL expects keyTimes with spline timing; synthesize even spacing for robustness.
            key_times = [index / (len(values) - 1) for index in range(len(values))]

        return key_times, key_points, key_splines

    def _get_animation_type(self, tag_name: str) -> AnimationType | None:
        mapping = {
            "animate": AnimationType.ANIMATE,
            "animateTransform": AnimationType.ANIMATE_TRANSFORM,
            "animateColor": AnimationType.ANIMATE_COLOR,
            "animateMotion": AnimationType.ANIMATE_MOTION,
            "set": AnimationType.SET,
        }
        return mapping.get(tag_name)

    @staticmethod
    def _extract_raw_attributes(element: etree._Element) -> dict[str, str]:
        attrs: dict[str, str] = {}
        for raw_name, value in element.attrib.items():
            qname = etree.QName(raw_name)
            if qname.namespace == "http://www.w3.org/1999/xlink":
                key = f"xlink:{qname.localname}"
            else:
                key = qname.localname
            attrs[key] = value
        return attrs

    def _ensure_target_ids(self, elements: list[etree._Element]) -> None:
        """Assign synthetic IDs to elements that are targets of animations but lack an ID."""
        counter = 0
        for element in elements:
            # Check if it has a target via href
            href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
            if href and href.startswith("#"):
                continue

            # Check parent
            parent = element.getparent()
            if parent is not None and not parent.get("id"):
                synthetic_id = f"anim-target-{counter}"
                parent.set("id", synthetic_id)
                counter += 1

    def _get_target_element_id(self, element: etree._Element) -> str | None:
        # 1. Standard href or xlink:href
        href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
        if href and href.startswith("#"):
            return href[1:]

        # 2. Parent fallback (now guaranteed to have an ID if it's an anim parent)
        parent = element.getparent()
        if parent is not None:
            parent_id = parent.get("id")
            if parent_id:
                return parent_id

        # 3. Non-standard target attribute
        target = element.get("target")
        if target and target.startswith("#"):
            return target[1:]

        return None

    # ------------------------------------------------------------------ #
    # Value resolution (stays in coordinator — depends on element lookup) #
    # ------------------------------------------------------------------ #
    def _resolve_underlying_animation_value(
        self,
        animation_element: etree._Element,
        *,
        target_attribute: str | None,
    ) -> str | None:
        if not target_attribute:
            return None

        target = self._resolve_target_element(animation_element)
        if target is None:
            return None

        direct_value = target.get(target_attribute)
        if direct_value is not None and direct_value.strip():
            return direct_value.strip()

        style_value = target.get("style")
        if not style_value:
            return None

        for declaration in style_value.split(";"):
            if ":" not in declaration:
                continue
            property_name, value = declaration.split(":", 1)
            if property_name.strip() == target_attribute and value.strip():
                return value.strip()

        return None

    # ------------------------------------------------------------------ #
    # Transform / motion parsing (stays — heavy element lookup use)      #
    # ------------------------------------------------------------------ #
    def _resolve_motion_path_reference(
        self,
        animation_element: etree._Element,
        href: str,
    ) -> str | None:
        """Resolve <mpath href="#..."> references to path data."""
        if not href.startswith("#"):
            return None

        target_id = href[1:].strip()
        if not target_id:
            return None

        root = animation_element.getroottree().getroot()
        matches = root.xpath(".//*[@id=$target_id]", target_id=target_id)
        if not matches:
            return None

        target = matches[0]
        if etree.QName(target).localname.lower() != "path":
            return None

        path_data = target.get("d")
        if not path_data:
            return None
        return path_data.strip()

    def _resolve_motion_space_matrix(
        self,
        animation_element: etree._Element,
        *,
        animation_type: AnimationType,
        target_attribute: str | None = None,
        transform_type: TransformType | None = None,
    ) -> tuple[float, float, float, float, float, float] | None:
        if not self._animation_uses_local_motion_space(
            animation_type=animation_type,
            target_attribute=target_attribute,
            transform_type=transform_type,
        ):
            return None

        target = self._resolve_target_element(animation_element)
        if target is None:
            return None

        matrix = Matrix2D.identity()
        lineage = [*target.iterancestors()][::-1]
        lineage.append(target)

        for node in lineage:
            transform_attr = node.get("transform")
            if transform_attr:
                matrix = matrix.multiply(parse_transform_list(transform_attr))

        if matrix.is_identity():
            return None
        return matrix.as_tuple()

    @staticmethod
    def _animation_uses_local_motion_space(
        *,
        animation_type: AnimationType,
        target_attribute: str | None,
        transform_type: TransformType | None,
    ) -> bool:
        if animation_type == AnimationType.ANIMATE_MOTION:
            return True

        if animation_type == AnimationType.ANIMATE_TRANSFORM:
            return transform_type in {
                TransformType.TRANSLATE,
                TransformType.SCALE,
            }

        if animation_type != AnimationType.ANIMATE:
            return False

        return (target_attribute or "") in {
            "x",
            "y",
            "cx",
            "cy",
            "x1",
            "x2",
            "y1",
            "y2",
            "width",
            "height",
            "w",
            "h",
            "rx",
            "ry",
        }

    def _resolve_target_element(
        self,
        animation_element: etree._Element,
    ) -> etree._Element | None:
        root = animation_element.getroottree().getroot()

        href = animation_element.get("href") or animation_element.get("{http://www.w3.org/1999/xlink}href")
        if href and href.startswith("#"):
            target = self._lookup_element_by_id(root, href[1:])
            if target is not None:
                return target

        parent = animation_element.getparent()
        if parent is not None and etree.QName(parent).localname not in self._ANIMATION_TAGS:
            return parent

        target = animation_element.get("target")
        if target and target.startswith("#"):
            return self._lookup_element_by_id(root, target[1:])

        return None

    @staticmethod
    def _lookup_element_by_id(
        root: etree._Element,
        element_id: str,
    ) -> etree._Element | None:
        element_id = element_id.strip()
        if not element_id:
            return None

        matches = root.xpath(".//*[@id=$target_id]", target_id=element_id)
        if not matches:
            return None
        return matches[0]

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

    def _parse_motion_rotate(
        self,
        element: etree._Element,
        animation_type: AnimationType,
    ) -> str | None:
        if animation_type != AnimationType.ANIMATE_MOTION:
            return None

        rotate = element.get("rotate")
        if rotate is None:
            return None

        rotate = rotate.strip()
        if not rotate:
            return None
        return rotate

    # ------------------------------------------------------------------ #
    # Summary helpers                                                    #
    # ------------------------------------------------------------------ #
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

    def _record_degradation(self, reason: str) -> None:
        self._degradation_reasons[reason] = self._degradation_reasons.get(reason, 0) + 1


__all__ = ["SMILParser", "SMILParsingError", "ParsedAnimation"]
