"""SMIL animation parser that converts SVG elements into animation IR."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D, parse_transform_list
from svg2ooxml.common.time import parse_time_value
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationSummary,
    AnimationTiming,
    AnimationType,
    BeginTrigger,
    BeginTriggerType,
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
    _TIME_OFFSET_RE = re.compile(
        r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:ms|s|min|h)?$",
        re.IGNORECASE,
    )
    _ELEMENT_EVENT_RE = re.compile(
        r"^([A-Za-z_][\w.\-]*)\.([A-Za-z_][\w.\-]*)\s*([+-].+)?$",
        re.IGNORECASE,
    )
    _REPEAT_EVENT_RE = re.compile(
        r"^([A-Za-z_][\w.\-]*)\.repeat\(([^)]+)\)\s*([+-].+)?$",
        re.IGNORECASE,
    )
    _ACCESS_KEY_RE = re.compile(
        r"^accessKey\(([^)]+)\)\s*([+-].+)?$",
        re.IGNORECASE,
    )
    _WALLCLOCK_RE = re.compile(
        r"^wallclock\(([^)]+)\)\s*([+-].+)?$",
        re.IGNORECASE,
    )
    _CLICK_OFFSET_RE = re.compile(
        r"^click\s*([+-].+)$",
        re.IGNORECASE,
    )
    _NUMBER_LIST_SPLIT_RE = re.compile(r"[,\s]+")

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
        values = self._parse_animation_values(
            element,
            animation_type,
            target_attribute=target_attribute,
        )
        if not values:
            raise SMILParsingError("Animation missing values")

        timing = self._parse_timing(element)
        key_times = self._parse_key_times(element)
        key_points = self._parse_key_points(element, animation_type)
        key_splines = self._parse_key_splines(element)
        calc_mode = self._parse_calc_mode(element, animation_type)
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

    def _parse_animation_values(
        self,
        element: etree._Element,
        animation_type: AnimationType,
        *,
        target_attribute: str | None,
    ) -> list[str]:
        if animation_type == AnimationType.ANIMATE_MOTION:
            path = element.get("path")
            if path:
                return [path.strip()]
            mpath = (
                element.find(".//mpath")
                or element.find(".//svg:mpath", namespaces=self._namespace_map)
            )
            if mpath is not None:
                href = mpath.get("href", mpath.get("{http://www.w3.org/1999/xlink}href"))
                if href:
                    resolved = self._resolve_motion_path_reference(element, href.strip())
                    if resolved is not None:
                        return [resolved]
                    self.animation_summary.add_warning(
                        f"animateMotion mpath reference unresolved: {href}"
                    )
                    self._record_degradation("mpath_reference_unresolved")
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
                endpoint = self._combine_numeric_values(from_val, by_val, operator="+")
                return [
                    f"M {from_val.strip()} L {(endpoint or by_val).strip()}"
                ]
            if to_val and by_val:
                startpoint = self._combine_numeric_values(to_val, by_val, operator="-")
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
            endpoint = self._combine_numeric_values(from_value, by_value, operator="+")
            return [from_value.strip(), endpoint or by_value.strip()]

        if to_value is not None and by_value is not None:
            startpoint = self._combine_numeric_values(to_value, by_value, operator="-")
            return [startpoint or by_value.strip(), to_value.strip()]

        if to_value is not None:
            underlying = self._resolve_underlying_animation_value(
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

    def _combine_numeric_values(
        self,
        left: str,
        right: str,
        *,
        operator: str,
    ) -> str | None:
        left_values = self._parse_numeric_list(left)
        right_values = self._parse_numeric_list(right)
        if left_values is None or right_values is None:
            self._record_degradation("by_value_non_numeric")
            return None
        if len(right_values) == 1 and len(left_values) > 1:
            right_values = right_values * len(left_values)
        if len(left_values) != len(right_values):
            self._record_degradation("by_value_dimension_mismatch")
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
        return " ".join(self._format_number(value) for value in combined)

    def _parse_numeric_list(self, value: str) -> list[float] | None:
        tokens = [
            token
            for token in self._NUMBER_LIST_SPLIT_RE.split(value.strip())
            if token
        ]
        if not tokens:
            return None
        try:
            return [float(token) for token in tokens]
        except ValueError:
            return None

    @staticmethod
    def _format_number(value: float) -> str:
        if abs(value) < 1e-12:
            return "0"
        return f"{value:.12g}"

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

    def _parse_timing(self, element: etree._Element) -> AnimationTiming:
        begin, begin_triggers = self._parse_begin(element.get("begin"))
        end_triggers = self._parse_end(element.get("end"))
        dur_value = element.get("dur", "1s")
        duration = float("inf") if dur_value == "indefinite" else parse_time_value(dur_value)
        repeat_duration = self._parse_optional_duration(element.get("repeatDur"))

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
            repeat_duration=repeat_duration,
            fill_mode=fill_mode,
            begin_triggers=begin_triggers,
            end_triggers=end_triggers,
        )

    @staticmethod
    def _parse_optional_duration(value: str | None) -> float | None:
        if not value or value == "indefinite":
            return None
        return parse_time_value(value)

    def _parse_begin(self, begin_attr: str | None) -> tuple[float, list[BeginTrigger] | None]:
        """Parse SMIL begin expression(s) into fallback seconds and trigger metadata."""
        if begin_attr is None:
            return (0.0, [BeginTrigger(trigger_type=BeginTriggerType.TIME_OFFSET, delay_seconds=0.0)])

        begin_text = begin_attr.strip()
        if not begin_text:
            return (0.0, [BeginTrigger(trigger_type=BeginTriggerType.TIME_OFFSET, delay_seconds=0.0)])

        tokens = [token.strip() for token in begin_text.split(";") if token.strip()]
        parsed: list[BeginTrigger] = []
        for token in tokens:
            trigger = self._parse_begin_token(token)
            if trigger is None:
                self.animation_summary.add_warning(f"Invalid begin expression: {token}")
                self._record_degradation("begin_expression_invalid")
                continue
            parsed.append(trigger)

        if not parsed:
            self._record_degradation("begin_fallback_default_zero")
            return (0.0, [BeginTrigger(trigger_type=BeginTriggerType.TIME_OFFSET, delay_seconds=0.0)])

        # Backward-compatible numeric begin fallback used by existing timing helpers.
        begin_seconds = 0.0
        for trigger in parsed:
            if trigger.trigger_type == BeginTriggerType.TIME_OFFSET and trigger.target_element_id is None:
                begin_seconds = trigger.delay_seconds
                break

        return (begin_seconds, parsed)

    def _parse_end(self, end_attr: str | None) -> list[BeginTrigger] | None:
        """Parse SMIL end expressions for IR plumbing.

        The writer does not yet fully realize end conditions natively; this
        keeps them visible to later policy and emitter work.
        """
        if end_attr is None:
            return None

        end_text = end_attr.strip()
        if not end_text:
            return None

        parsed: list[BeginTrigger] = []
        for token in [part.strip() for part in end_text.split(";") if part.strip()]:
            trigger = self._parse_begin_token(token)
            if trigger is None:
                self.animation_summary.add_warning(f"Invalid end expression: {token}")
                self._record_degradation("end_expression_invalid")
                continue
            parsed.append(trigger)

        return parsed or None

    def _parse_begin_token(self, token: str) -> BeginTrigger | None:
        raw_token = token.strip()
        lowered = raw_token.lower()
        if not raw_token:
            return None
        if lowered == "indefinite":
            return BeginTrigger(trigger_type=BeginTriggerType.INDEFINITE)
        if lowered == "click":
            return BeginTrigger(trigger_type=BeginTriggerType.CLICK)
        click_offset_match = self._CLICK_OFFSET_RE.match(lowered)
        if click_offset_match:
            offset_value = re.sub(r"\s+", "", click_offset_match.group(1).strip())
            if not self._TIME_OFFSET_RE.match(offset_value):
                return None
            return BeginTrigger(
                trigger_type=BeginTriggerType.CLICK,
                delay_seconds=parse_time_value(offset_value),
            )
        if self._TIME_OFFSET_RE.match(lowered):
            return BeginTrigger(
                trigger_type=BeginTriggerType.TIME_OFFSET,
                delay_seconds=parse_time_value(lowered),
            )

        repeat_match = self._REPEAT_EVENT_RE.match(raw_token)
        if repeat_match:
            target_element_id, repeat_iteration, offset_expr = repeat_match.groups()
            delay_seconds = self._parse_optional_offset_seconds(offset_expr)
            if delay_seconds is None:
                return None
            repeat_iteration = repeat_iteration.strip()
            return BeginTrigger(
                trigger_type=BeginTriggerType.ELEMENT_REPEAT,
                delay_seconds=delay_seconds,
                target_element_id=target_element_id,
                event_name="repeat",
                repeat_iteration=(
                    int(repeat_iteration)
                    if repeat_iteration.isdigit()
                    else repeat_iteration
                ),
            )

        access_key_match = self._ACCESS_KEY_RE.match(raw_token)
        if access_key_match:
            access_key, offset_expr = access_key_match.groups()
            delay_seconds = self._parse_optional_offset_seconds(offset_expr)
            if delay_seconds is None:
                return None
            return BeginTrigger(
                trigger_type=BeginTriggerType.ACCESS_KEY,
                delay_seconds=delay_seconds,
                access_key=access_key.strip(),
            )

        wallclock_match = self._WALLCLOCK_RE.match(raw_token)
        if wallclock_match:
            wallclock_value, offset_expr = wallclock_match.groups()
            delay_seconds = self._parse_optional_offset_seconds(offset_expr)
            if delay_seconds is None:
                return None
            return BeginTrigger(
                trigger_type=BeginTriggerType.WALLCLOCK,
                delay_seconds=delay_seconds,
                wallclock_value=wallclock_value.strip(),
            )

        match = self._ELEMENT_EVENT_RE.match(raw_token)
        if not match:
            return None

        target_element_id, event_name, offset_expr = match.groups()
        delay_seconds = self._parse_optional_offset_seconds(offset_expr)
        if delay_seconds is None:
            return None

        event_name = event_name.lower()
        if event_name == "click":
            trigger_type = BeginTriggerType.CLICK
        elif event_name == "begin":
            trigger_type = BeginTriggerType.ELEMENT_BEGIN
        elif event_name == "end":
            trigger_type = BeginTriggerType.ELEMENT_END
        else:
            trigger_type = BeginTriggerType.EVENT

        return BeginTrigger(
            trigger_type=trigger_type,
            delay_seconds=delay_seconds,
            target_element_id=target_element_id,
            event_name=event_name,
        )

    def _parse_optional_offset_seconds(self, offset_expr: str | None) -> float | None:
        if not offset_expr:
            return 0.0
        offset_value = re.sub(r"\s+", "", offset_expr.strip())
        if not self._TIME_OFFSET_RE.match(offset_value):
            return None
        return parse_time_value(offset_value)

    def _parse_key_times(self, element: etree._Element) -> list[float] | None:
        attr = element.get("keyTimes")
        if not attr:
            return None

        try:
            values = [float(value.strip()) for value in attr.split(";") if value.strip()]
        except (ValueError, TypeError):
            self.animation_summary.add_warning("Invalid keyTimes format")
            self._record_degradation("key_times_invalid_format")
            return None

        if not all(0.0 <= value <= 1.0 for value in values):
            self.animation_summary.add_warning("keyTimes values outside [0,1] range")
            self._record_degradation("key_times_out_of_range")
            return None
        if values != sorted(values):
            self.animation_summary.add_warning("keyTimes must be in ascending order")
            self._record_degradation("key_times_not_ascending")
            return None

        return values or None

    def _parse_key_points(
        self,
        element: etree._Element,
        animation_type: AnimationType,
    ) -> list[float] | None:
        attr = element.get("keyPoints")
        if not attr:
            return None

        try:
            values = [float(value.strip()) for value in attr.split(";") if value.strip()]
        except (ValueError, TypeError):
            self.animation_summary.add_warning("Invalid keyPoints format")
            self._record_degradation("key_points_invalid_format")
            return None

        if not all(0.0 <= value <= 1.0 for value in values):
            self.animation_summary.add_warning("keyPoints values outside [0,1] range")
            self._record_degradation("key_points_out_of_range")
            return None

        if animation_type != AnimationType.ANIMATE_MOTION:
            self.animation_summary.add_warning(
                "Ignoring keyPoints because animation is not animateMotion"
            )
            self._record_degradation("key_points_non_motion")
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
            self._record_degradation("key_splines_invalid_format")
            return None

        return splines or None

    def _parse_calc_mode(
        self,
        element: etree._Element,
        animation_type: AnimationType,
    ) -> CalcMode:
        attr = (element.get("calcMode") or "").strip().lower()
        mapping = {
            "linear": CalcMode.LINEAR,
            "discrete": CalcMode.DISCRETE,
            "paced": CalcMode.PACED,
            "spline": CalcMode.SPLINE,
        }
        if not attr:
            if animation_type == AnimationType.ANIMATE_MOTION:
                return CalcMode.PACED
            return CalcMode.LINEAR
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
