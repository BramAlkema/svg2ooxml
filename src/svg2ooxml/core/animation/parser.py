"""SMIL animation parser that converts SVG elements into animation IR."""

from __future__ import annotations

from collections.abc import Iterable

from lxml import etree

from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationSummary,
    AnimationType,
    CalcMode,
    TransformType,
)

from . import interpolation as _interpolation
from . import motion_context as _motion
from . import summary as _summary
from . import targeting as _targeting
from . import timing_parser as _timing
from . import value_parser as _values
from .parser_types import (
    ANIMATION_TAGS,
    ParsedAnimation,
    SMILParsingError,
    get_animation_type,
)
from .parser_types import (
    parse_optional_duration_ms as _parse_optional_duration_ms,
)


class SMILParser:
    """Parse SMIL animation elements within an SVG DOM."""

    _ANIMATION_TAGS = ANIMATION_TAGS

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
        self.reset_summary()
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
        return _targeting.find_animation_elements(
            svg_element,
            animation_tags=self._ANIMATION_TAGS,
        )

    def _parse_animation_element(self, element: etree._Element) -> AnimationDefinition | None:
        tag_name = etree.QName(element).localname
        animation_type = self._get_animation_type(tag_name)
        if not animation_type:
            raise SMILParsingError(f"Unknown animation type: {tag_name}")

        element_id = self._get_target_element_id(element)
        if not element_id:
            raise SMILParsingError("Animation missing target element")
        target_element = self._resolve_target_element(element)

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
            raw_attributes=self._extract_raw_attributes(
                element,
                target_element=target_element,
            ),
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
        return _interpolation.sanitize_interpolation_inputs(
            animation_type=animation_type,
            values=values,
            calc_mode=calc_mode,
            key_times=key_times,
            key_points=key_points,
            key_splines=key_splines,
            animation_summary=self.animation_summary,
            record_degradation=self._record_degradation,
        )

    def _get_animation_type(self, tag_name: str) -> AnimationType | None:
        return get_animation_type(tag_name)

    @staticmethod
    def _extract_raw_attributes(
        element: etree._Element,
        *,
        target_element: etree._Element | None = None,
    ) -> dict[str, str]:
        return _targeting.extract_raw_attributes(
            element,
            target_element=target_element,
        )

    def _ensure_target_ids(self, elements: list[etree._Element]) -> None:
        _targeting.ensure_target_ids(elements)

    def _get_target_element_id(self, element: etree._Element) -> str | None:
        return _targeting.get_target_element_id(element)

    def _resolve_underlying_animation_value(
        self,
        animation_element: etree._Element,
        *,
        target_attribute: str | None,
    ) -> str | None:
        return _targeting.resolve_underlying_animation_value(
            animation_element,
            target_attribute=target_attribute,
            animation_tags=self._ANIMATION_TAGS,
        )

    def _resolve_motion_path_reference(
        self,
        animation_element: etree._Element,
        href: str,
    ) -> str | None:
        return _motion.resolve_motion_path_reference(animation_element, href)

    def _resolve_motion_space_matrix(
        self,
        animation_element: etree._Element,
        *,
        animation_type: AnimationType,
        target_attribute: str | None = None,
        transform_type: TransformType | None = None,
    ) -> tuple[float, float, float, float, float, float] | None:
        return _motion.resolve_motion_space_matrix(
            animation_element,
            animation_type=animation_type,
            target_attribute=target_attribute,
            transform_type=transform_type,
            animation_tags=self._ANIMATION_TAGS,
        )

    @staticmethod
    def _animation_uses_local_motion_space(
        *,
        animation_type: AnimationType,
        target_attribute: str | None,
        transform_type: TransformType | None,
    ) -> bool:
        return _motion.animation_uses_local_motion_space(
            animation_type=animation_type,
            target_attribute=target_attribute,
            transform_type=transform_type,
        )

    def _resolve_target_element(
        self,
        animation_element: etree._Element,
    ) -> etree._Element | None:
        return _targeting.resolve_target_element(
            animation_element,
            animation_tags=self._ANIMATION_TAGS,
        )

    @staticmethod
    def _lookup_element_by_id(
        root: etree._Element,
        element_id: str,
    ) -> etree._Element | None:
        return _targeting.lookup_element_by_id(root, element_id)

    def _parse_transform_type(
        self,
        element: etree._Element,
        animation_type: AnimationType,
    ) -> TransformType | None:
        return _motion.parse_transform_type(element, animation_type)

    def _parse_motion_rotate(
        self,
        element: etree._Element,
        animation_type: AnimationType,
    ) -> str | None:
        return _motion.parse_motion_rotate(element, animation_type)

    # ------------------------------------------------------------------ #
    # Summary helpers                                                    #
    # ------------------------------------------------------------------ #
    def _update_summary(self, animation: AnimationDefinition) -> None:
        _summary.update_summary(self.animation_summary, animation)

    def _finalize_summary(self, animations: list[AnimationDefinition]) -> None:
        _summary.finalize_summary(self.animation_summary, animations)

    def _record_degradation(self, reason: str) -> None:
        _summary.record_degradation(self._degradation_reasons, reason)


__all__ = ["SMILParser", "SMILParsingError", "ParsedAnimation"]
