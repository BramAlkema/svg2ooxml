"""Translate-path helpers for transform animations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.common.geometry.matrix import transform_delta_pairs
from svg2ooxml.drawingml.animation.timing_utils import compute_paced_key_times_2d
from svg2ooxml.drawingml.xml_builder import p_elem, p_sub
from svg2ooxml.ir.animation import CalcMode

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition


class TransformTranslateMixin:
    """Translate animation helpers used by ``TransformAnimationHandler``."""

    def _build_translate_element(
        self,
        animation: AnimationDefinition,
        behavior_id: int,
        translation_pairs: list[tuple[float, float]],
    ) -> etree._Element | None:
        if len(translation_pairs) < 2:
            return None

        translation_pairs = self._project_translation_pairs(
            animation,
            translation_pairs,
        )

        # Multi-keyframe: build a motion path with M/L segments
        if len(translation_pairs) > 2:
            return self._build_translate_path_element(
                animation,
                behavior_id,
                translation_pairs,
            )

        # Simple 2-value: use a relative motion path so PowerPoint interprets
        # the delta in slide coordinates rather than raw EMUs.
        start_dx, start_dy = translation_pairs[0]
        end_dx, end_dy = translation_pairs[-1]
        viewport_w, viewport_h = self._resolve_motion_viewport_px(animation)
        delta_x = (end_dx - start_dx) / viewport_w
        delta_y = (end_dy - start_dy) / viewport_h

        anim_motion = p_elem(
            "animMotion",
            origin="layout",
            path=(
                f"M 0 0 L {self._format_coord(delta_x)} "
                f"{self._format_coord(delta_y)} E"
            ),
            pathEditMode="relative",
            rAng="0",
            ptsTypes="AA",
        )

        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            attr_name_list=["ppt_x", "ppt_y"],
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim_motion.append(cBhvr)

        # ECMA-376 requires a choice element (by/from/to/rCtr) after cBhvr
        p_sub(anim_motion, "rCtr", x="0", y="0")

        return anim_motion

    def _build_translate_path_element(
        self,
        animation: AnimationDefinition,
        behavior_id: int,
        translation_pairs: list[tuple[float, float]],
    ) -> etree._Element:
        """Build ``<p:animMotion>`` with path for multi-keyframe translate."""
        viewport_w, viewport_h = self._resolve_motion_viewport_px(animation)
        start_x, start_y = translation_pairs[0]

        path_pairs = list(translation_pairs)
        key_times = animation.key_times
        calc_mode_value = (
            animation.calc_mode.value
            if isinstance(animation.calc_mode, CalcMode)
            else str(animation.calc_mode).lower()
        )

        if calc_mode_value == CalcMode.PACED.value and len(path_pairs) > 2:
            paced_times = compute_paced_key_times_2d(path_pairs)
            if paced_times is not None:
                key_times = paced_times

        path_pairs = self._retime_translate_pairs(
            pairs=path_pairs,
            key_times=key_times,
            calc_mode=calc_mode_value,
        )

        # Build M/L path string in slide-fraction coordinates
        segments: list[str] = []
        for i, (x_px, y_px) in enumerate(path_pairs):
            dx_px = x_px - start_x
            dy_px = y_px - start_y
            nx = dx_px / viewport_w
            ny = dy_px / viewport_h

            cmd = "M" if i == 0 else "L"
            segments.append(f"{cmd} {self._format_coord(nx)} {self._format_coord(ny)}")

        path = " ".join(segments) + " E"
        pts_types = "A" * len(path_pairs)

        anim_motion = p_elem(
            "animMotion",
            origin="layout",
            path=path,
            pathEditMode="relative",
            rAng="0",
            ptsTypes=pts_types,
        )

        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            attr_name_list=["ppt_x", "ppt_y"],
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim_motion.append(cBhvr)

        # ECMA-376 requires a choice element (by/from/to/rCtr) after cBhvr
        p_sub(anim_motion, "rCtr", x="0", y="0")

        return anim_motion

    @staticmethod
    def _project_translation_pairs(
        animation: AnimationDefinition,
        pairs: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        return transform_delta_pairs(animation.motion_space_matrix, pairs)

    @classmethod
    def _retime_translate_pairs(
        cls,
        *,
        pairs: list[tuple[float, float]],
        key_times: list[float] | None,
        calc_mode: CalcMode | str,
        segment_budget: int = 96,
    ) -> list[tuple[float, float]]:
        """Approximate keyTimes/calcMode timing by expanding path vertices."""
        if len(pairs) < 2 or key_times is None or len(key_times) != len(pairs):
            return pairs

        calc_mode_value = (
            calc_mode.value
            if isinstance(calc_mode, CalcMode)
            else str(calc_mode).lower()
        )
        if calc_mode_value == CalcMode.DISCRETE.value:
            return cls._expand_discrete_pairs(
                pairs=pairs,
                key_times=key_times,
                segment_budget=segment_budget,
            )

        return cls._retime_linear_pairs(
            pairs=pairs,
            key_times=key_times,
            segment_budget=segment_budget,
        )

    @staticmethod
    def _retime_linear_pairs(
        *,
        pairs: list[tuple[float, float]],
        key_times: list[float],
        segment_budget: int,
    ) -> list[tuple[float, float]]:
        if len(pairs) < 2:
            return pairs

        expanded: list[tuple[float, float]] = [pairs[0]]
        for index in range(1, len(pairs)):
            start = pairs[index - 1]
            end = pairs[index]
            duration = max(0.0, key_times[index] - key_times[index - 1])
            segment_count = max(1, int(round(duration * segment_budget)))

            for step in range(1, segment_count + 1):
                t = step / segment_count
                x = start[0] + (end[0] - start[0]) * t
                y = start[1] + (end[1] - start[1]) * t
                expanded.append((x, y))

        return expanded

    @staticmethod
    def _expand_discrete_pairs(
        *,
        pairs: list[tuple[float, float]],
        key_times: list[float],
        segment_budget: int,
    ) -> list[tuple[float, float]]:
        if len(pairs) < 2:
            return pairs

        expanded: list[tuple[float, float]] = [pairs[0]]
        for index in range(1, len(pairs)):
            prev = pairs[index - 1]
            curr = pairs[index]
            duration = max(0.0, key_times[index] - key_times[index - 1])
            slot_count = max(1, int(round(duration * segment_budget)))

            for _ in range(max(0, slot_count - 1)):
                expanded.append(prev)
            expanded.append(curr)

        return expanded
