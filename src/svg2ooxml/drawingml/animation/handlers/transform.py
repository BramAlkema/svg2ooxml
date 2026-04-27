"""Transform animation handler.

Generates PowerPoint ``<p:animScale>``, ``<p:animRot>``, or ``<p:animMotion>``
elements for ``<animateTransform>`` animations (scale, rotate, translate, matrix).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.common.conversions.angles import degrees_to_ppt
from svg2ooxml.common.units import emu_to_px
from svg2ooxml.drawingml.animation.oracle import default_oracle
from svg2ooxml.ir.animation import BeginTriggerType, CalcMode, TransformType

from .base import AnimationHandler
from .transform_matrix import TransformMatrixMixin
from .transform_rotate import (
    build_multi_keyframe_rotate,
    build_rotate_element,
    build_rotate_with_orbit,
    compute_orbit_offset,
    extract_rotation_center,
)
from .transform_scale import build_scale_element, build_scale_origin_motion
from .transform_translate import TransformTranslateMixin

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = ["TransformAnimationHandler"]


class TransformAnimationHandler(
    TransformMatrixMixin,
    TransformTranslateMixin,
    AnimationHandler,
):
    """Handler for transform animations (scale, rotate, translate, matrix)."""

    _SUPPORTED_TRANSFORMS = {
        TransformType.SCALE,
        TransformType.ROTATE,
        TransformType.TRANSLATE,
        TransformType.MATRIX,
    }

    def can_handle(self, animation: AnimationDefinition) -> bool:
        if animation.transform_type is None:
            return False
        return animation.transform_type in self._SUPPORTED_TRANSFORMS

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element | None:
        """Build ``<p:par>`` wrapping the appropriate transform animation element."""
        transform_type = animation.transform_type
        if transform_type is None:
            return None

        preset_class: str | None = None
        preset_id: int | None = None

        if transform_type == TransformType.SCALE:
            scale_pairs = [
                self._processor.parse_scale_pair(v) for v in animation.values
            ]
            child = build_scale_element(
                self._xml, animation, behavior_id, scale_pairs
            )
            if child is None:
                return None
            scale_motion = build_scale_origin_motion(
                xml=self._xml,
                animation=animation,
                behavior_id=behavior_id + 2,
                scale_pairs=scale_pairs,
                viewport_px=self._resolve_motion_viewport_px(animation),
                format_coord=self._format_coord,
            )
            if scale_motion is not None:
                return self._xml.build_par_container_with_children_elem(
                    par_id=par_id,
                    duration_ms=animation.duration_ms,
                    delay_ms=animation.begin_ms,
                    child_elements=[child, scale_motion],
                    preset_id=6,
                    preset_class="emph",
                    preset_subtype=0,
                    node_type="clickEffect",
                    begin_triggers=animation.begin_triggers,
                    default_target_shape=animation.element_id,
                    effect_group_id=par_id,
                )
            preset_class = "emph"
            preset_id = 6  # Grow/Shrink
        elif transform_type == TransformType.ROTATE:
            parsed = [self._parse_rotate_value(v) for v in animation.values]
            angles = [p[0] for p in parsed]
            rotation_center = extract_rotation_center(parsed)

            if animation.calc_mode == CalcMode.DISCRETE and len(angles) > 1:
                return self._build_discrete_rotate_sets(
                    animation, par_id, behavior_id, angles
                )

            if len(angles) > 2:
                return build_multi_keyframe_rotate(
                    xml=self._xml,
                    processor=self._processor,
                    units=self._units,
                    animation=animation,
                    par_id=par_id,
                    behavior_id=behavior_id,
                    angles=angles,
                    format_coord=self._format_coord,
                    slide_size=self._get_motion_slide_size(animation),
                    rotation_center=rotation_center,
                )

            # Check if we need a companion orbital motion path
            orbit_offset = compute_orbit_offset(
                rotation_center,
                animation.element_center_px,
            )
            if orbit_offset is not None:
                return build_rotate_with_orbit(
                    xml=self._xml,
                    processor=self._processor,
                    units=self._units,
                    animation=animation,
                    par_id=par_id,
                    behavior_id=behavior_id,
                    angles=angles,
                    orbit_offset=orbit_offset,
                    format_coord=self._format_coord,
                    slide_size=self._get_motion_slide_size(animation),
                )

            child = build_rotate_element(
                self._xml, self._processor, animation, behavior_id, angles
            )
            preset_class = "emph"
            preset_id = 8  # Spin
        elif transform_type == TransformType.TRANSLATE:
            translation_pairs = [
                self._processor.parse_translation_pair(v) for v in animation.values
            ]
            child = self._build_translate_element(
                animation, behavior_id, translation_pairs
            )
            preset_class = "path"
            preset_id = 0  # Custom Path
        elif transform_type == TransformType.MATRIX:
            child, preset_class = self._build_matrix_element(animation, behavior_id)
        else:
            return None

        if child is None:
            return None

        if self._transform_uses_oracle(animation):
            oracle_par = self._try_instantiate_transform_oracle(
                animation=animation,
                par_id=par_id,
                behavior_id=behavior_id,
                preset_class=preset_class,
                preset_id=preset_id,
                child=child,
            )
            if oracle_par is not None:
                return oracle_par

        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=child,
            preset_id=preset_id,
            preset_class=preset_class,
            preset_subtype=0 if preset_id else None,
            node_type="clickEffect",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
        )

    # ------------------------------------------------------------------ #
    # Oracle                                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _transform_uses_oracle(animation: AnimationDefinition) -> bool:
        """Gate the oracle fast-path to simple start-conditions only.

        The templates emit a single ``<p:cond delay="{DELAY_MS}"/>`` and do
        not express ``additive``, ``repeatCount``, event-based begin triggers,
        multi-keyframe sequences, or custom ``keyTimes``. Any of those →
        fall through to the imperative builder.
        """
        if (animation.additive or "replace").lower() == "sum":
            return False
        if animation.repeat_count not in (None, 1, "1"):
            return False
        if len(animation.values) > 2:
            return False
        if animation.key_times:
            return False
        if animation.calc_mode in {CalcMode.DISCRETE, CalcMode.SPLINE}:
            return False
        if animation.key_splines:
            return False
        triggers = animation.begin_triggers
        if triggers:
            if len(triggers) > 1:
                return False
            if triggers[0].trigger_type != BeginTriggerType.TIME_OFFSET:
                return False
        return True

    def _try_instantiate_transform_oracle(
        self,
        *,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        preset_class: str | None,
        preset_id: int | None,
        child: etree._Element,
    ) -> etree._Element | None:
        """Return an oracle-driven par for the simple transform preset slots.

        Only ``emph/scale`` (preset 6), ``emph/rotate`` (preset 8), and
        ``path/motion`` (preset class ``path``) are currently wired. The
        remaining imperative paths handle multi-keyframe and composed effects
        which don't fit the single-template shape.
        """
        from svg2ooxml.drawingml.xml_builder import NS_P

        inner_fill = "hold" if animation.fill_mode == "freeze" else "remove"
        if preset_class == "emph" and preset_id == 6:
            scale_from = child.find(f"{{{NS_P}}}from")
            scale_to = child.find(f"{{{NS_P}}}to")
            if scale_from is None or scale_to is None:
                return None
            return default_oracle().instantiate(
                "emph/scale",
                shape_id=animation.element_id,
                par_id=par_id,
                duration_ms=animation.duration_ms,
                delay_ms=animation.begin_ms,
                BEHAVIOR_ID=behavior_id,
                FROM_X=scale_from.get("x", "100000"),
                FROM_Y=scale_from.get("y", "100000"),
                TO_X=scale_to.get("x", "100000"),
                TO_Y=scale_to.get("y", "100000"),
                INNER_FILL=inner_fill,
            )
        if preset_class == "emph" and preset_id == 8:
            rotation_by = child.get("by")
            if rotation_by is None:
                return None
            return default_oracle().instantiate(
                "emph/rotate",
                shape_id=animation.element_id,
                par_id=par_id,
                duration_ms=animation.duration_ms,
                delay_ms=animation.begin_ms,
                BEHAVIOR_ID=behavior_id,
                ROTATION_BY=rotation_by,
                INNER_FILL=inner_fill,
            )
        if preset_class == "path":
            path_data = child.get("path")
            if path_data is None:
                return None
            return default_oracle().instantiate(
                "path/motion",
                shape_id=animation.element_id,
                par_id=par_id,
                duration_ms=animation.duration_ms,
                delay_ms=animation.begin_ms,
                BEHAVIOR_ID=behavior_id,
                PATH_DATA=path_data,
                NODE_TYPE="clickEffect",
                INNER_FILL=inner_fill,
            )
        return None

    # ------------------------------------------------------------------ #
    # Rotate helpers (kept in coordinator)                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_rotate_value(value: str) -> tuple[float, float | None, float | None]:
        """Parse ``"angle [cx cy]"`` → ``(angle, cx, cy)``."""
        from svg2ooxml.common.conversions.transforms import parse_numeric_list

        nums = parse_numeric_list(value)
        if len(nums) >= 3:
            return (nums[0], nums[1], nums[2])
        if nums:
            return (nums[0], None, None)
        return (0.0, None, None)

    def _build_discrete_rotate_sets(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        angles: list[float],
    ) -> etree._Element:
        formatted = [str(degrees_to_ppt(a)) for a in angles]
        return self._build_discrete_set_sequence(
            animation, par_id, behavior_id, "style.rotation", formatted
        )

    # ------------------------------------------------------------------ #
    # Shared helpers                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_slide_size() -> tuple[int, int]:
        from svg2ooxml.drawingml.writer import DEFAULT_SLIDE_SIZE

        return DEFAULT_SLIDE_SIZE

    def _get_motion_slide_size(
        self,
        animation: AnimationDefinition,
    ) -> tuple[int, int]:
        viewport_w, viewport_h = self._resolve_motion_viewport_px(animation)
        return (
            max(int(round(self._units.to_emu(viewport_w, axis="x"))), 1),
            max(int(round(self._units.to_emu(viewport_h, axis="y"))), 1),
        )

    @staticmethod
    def _format_coord(value: float) -> str:
        """Format normalised coordinate as a string."""
        if abs(value) < 1e-10:
            return "0"
        return f"{value:.6g}"

    def _resolve_motion_viewport_px(
        self,
        animation: AnimationDefinition,
    ) -> tuple[float, float]:
        if animation.motion_viewport_px is not None:
            width_px = max(float(animation.motion_viewport_px[0]), 1.0)
            height_px = max(float(animation.motion_viewport_px[1]), 1.0)
            return (width_px, height_px)

        from svg2ooxml.drawingml.writer import DEFAULT_SLIDE_SIZE

        return (
            max(float(emu_to_px(DEFAULT_SLIDE_SIZE[0])), 1.0),
            max(float(emu_to_px(DEFAULT_SLIDE_SIZE[1])), 1.0),
        )
