"""Transform animation handler.

Generates PowerPoint ``<p:animScale>``, ``<p:animRot>``, or ``<p:animMotion>``
elements for ``<animateTransform>`` animations (scale, rotate, translate, matrix).
"""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.common.units import emu_to_px
from svg2ooxml.drawingml.animation.oracle import default_oracle
from svg2ooxml.drawingml.animation.timing_utils import compute_paced_key_times_2d
from svg2ooxml.drawingml.xml_builder import p_elem, p_sub
from svg2ooxml.ir.animation import BeginTriggerType, CalcMode, TransformType

from .base import AnimationHandler
from .transform_rotate import (
    build_multi_keyframe_rotate,
    build_rotate_element,
    build_rotate_with_orbit,
    compute_orbit_offset,
    extract_rotation_center,
)
from .transform_scale import build_scale_element, build_scale_origin_motion

if TYPE_CHECKING:
    from svg2ooxml.common.geometry.matrix import Matrix2D
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = ["TransformAnimationHandler"]

_logger = logging.getLogger(__name__)


class TransformAnimationHandler(AnimationHandler):
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
                    slide_size=self._get_slide_size(),
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
                    slide_size=self._get_slide_size(),
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
        formatted = [str(int(round(a * 60000))) for a in angles]
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

    # ------------------------------------------------------------------ #
    # Translate                                                            #
    # ------------------------------------------------------------------ #

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
        matrix = animation.motion_space_matrix
        if matrix is None:
            return list(pairs)
        a, b, c, d, _e, _f = matrix
        return [
            (a * x + c * y, b * x + d * y)
            for x, y in pairs
        ]

    @staticmethod
    def _retime_translate_pairs(
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
            return TransformAnimationHandler._expand_discrete_pairs(
                pairs=pairs,
                key_times=key_times,
                segment_budget=segment_budget,
            )

        return TransformAnimationHandler._retime_linear_pairs(
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

    # ------------------------------------------------------------------ #
    # Matrix (decompose → delegate)                                        #
    # ------------------------------------------------------------------ #

    def _build_matrix_element(
        self,
        animation: AnimationDefinition,
        behavior_id: int,
    ) -> tuple[etree._Element | None, str]:
        """Build animation element from matrix values.

        Returns (element, preset_class) or (None, "entr") on failure.
        """
        from svg2ooxml.common.geometry.matrix import Matrix2D

        if not animation.values:
            return None, "entr"

        matrices: list[Matrix2D] = []
        for raw in animation.values:
            if not isinstance(raw, str):
                return None, "entr"
            tokens = [t for t in re.split(r"[\s,]+", raw.strip()) if t]
            if len(tokens) < 6:
                return None, "entr"
            try:
                values = [float(t) for t in tokens[:6]]
            except ValueError:
                return None, "entr"
            matrices.append(Matrix2D.from_values(*values))

        matrix_type: str | None = None
        staged: list[tuple[str, object | None]] = []

        for matrix in matrices:
            current_type, payload = self._classify_matrix(matrix)
            if current_type is None:
                return None, "entr"
            if matrix_type is None:
                if current_type != "identity":
                    matrix_type = current_type
            else:
                if current_type not in {"identity", matrix_type}:
                    return None, "entr"
            staged.append((current_type, payload))

        if matrix_type is None:
            return None, "entr"

        classified: list[object] = []
        for current_type, payload in staged:
            if current_type == "identity":
                classified.append(self._identity_payload(matrix_type))
            else:
                classified.append(
                    payload
                    if payload is not None
                    else self._identity_payload(matrix_type)
                )

        if matrix_type == "translate":
            pairs = [(float(x), float(y)) for x, y in classified]
            return self._build_translate_element(animation, behavior_id, pairs), "path"
        elif matrix_type == "scale":
            pairs = [(float(x), float(y)) for x, y in classified]
            return (
                build_scale_element(self._xml, animation, behavior_id, pairs),
                "entr",
            )
        elif matrix_type == "rotate":
            angles = [float(angle) for angle in classified]
            return (
                build_rotate_element(
                    self._xml, self._processor, animation, behavior_id, angles
                ),
                "entr",
            )

        return None, "entr"

    # ------------------------------------------------------------------ #
    # Matrix classification                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _classify_matrix(
        matrix: Matrix2D, *, tolerance: float = 1e-6
    ) -> tuple[str | None, object | None]:
        if not all(
            math.isfinite(v)
            for v in (matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f)
        ):
            return (None, None)

        if (
            abs(matrix.a - 1.0) <= tolerance
            and abs(matrix.d - 1.0) <= tolerance
            and abs(matrix.b) <= tolerance
            and abs(matrix.c) <= tolerance
            and abs(matrix.e) <= tolerance
            and abs(matrix.f) <= tolerance
        ):
            return ("identity", None)

        if (
            abs(matrix.a - 1.0) <= tolerance
            and abs(matrix.d - 1.0) <= tolerance
            and abs(matrix.b) <= tolerance
            and abs(matrix.c) <= tolerance
        ):
            return ("translate", (matrix.e, matrix.f))

        if (
            abs(matrix.b) <= tolerance
            and abs(matrix.c) <= tolerance
            and abs(matrix.e) <= tolerance
            and abs(matrix.f) <= tolerance
        ):
            return ("scale", (matrix.a, matrix.d))

        if (
            abs(matrix.e) <= tolerance
            and abs(matrix.f) <= tolerance
            and abs(matrix.c + matrix.b) <= tolerance
            and abs(matrix.a - matrix.d) <= tolerance
            and abs(matrix.a * matrix.a + matrix.b * matrix.b - 1.0) <= tolerance
            and abs(matrix.c * matrix.c + matrix.d * matrix.d - 1.0) <= tolerance
        ):
            angle_deg = math.degrees(math.atan2(matrix.b, matrix.a))
            return ("rotate", angle_deg)

        # Fall through to QR decomposition for composite matrices
        decomposed = TransformAnimationHandler._decompose_matrix(
            matrix, tolerance=tolerance
        )
        if decomposed is not None:
            return decomposed

        return (None, None)

    @staticmethod
    def _decompose_matrix(
        matrix: Matrix2D,
        *,
        tolerance: float = 1e-6,
    ) -> tuple[str, object] | None:
        """Decompose a composite 2D affine matrix via QR decomposition.

        Extracts (translate, angle, scale) and returns the dominant
        non-trivial component as ``(type, payload)``.

        Returns ``None`` if the matrix contains skew (no PPT equivalent)
        or if no dominant component can be identified.
        """
        import logging

        # Extract translation directly
        tx, ty = matrix.e, matrix.f

        # Scale x = length of first column vector
        sx = math.sqrt(matrix.a**2 + matrix.b**2)
        if sx < tolerance:
            return None  # Degenerate matrix

        # Rotation angle from first column
        angle_deg = math.degrees(math.atan2(matrix.b, matrix.a))

        # Determine sy from determinant (preserves sign for reflections)
        det = matrix.a * matrix.d - matrix.b * matrix.c
        sy = det / sx

        # Verify no skew: reconstruct and compare
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        expected_c = -sy * sin_a
        expected_d = sy * cos_a

        if (
            abs(matrix.c - expected_c) > tolerance
            or abs(matrix.d - expected_d) > tolerance
        ):
            logging.getLogger(__name__).debug(
                "Matrix contains skew — cannot decompose for PowerPoint"
            )
            return None

        # Classify which components are non-trivial
        has_translate = abs(tx) > tolerance or abs(ty) > tolerance
        has_rotate = abs(angle_deg) > tolerance
        has_scale = abs(sx - 1.0) > tolerance or abs(sy - 1.0) > tolerance

        # Pick the dominant component
        if has_translate and not has_rotate and not has_scale:
            return ("translate", (tx, ty))
        if has_rotate and not has_translate and not has_scale:
            return ("rotate", angle_deg)
        if has_scale and not has_translate and not has_rotate:
            return ("scale", (sx, sy))

        # Composite: pick dominant based on priority (translate > rotate > scale)
        if has_translate:
            return ("translate", (tx, ty))
        if has_rotate:
            return ("rotate", angle_deg)
        if has_scale:
            return ("scale", (sx, sy))

        return None

    @staticmethod
    def _identity_payload(matrix_type: str) -> object:
        if matrix_type == "translate":
            return (0.0, 0.0)
        if matrix_type == "scale":
            return (1.0, 1.0)
        if matrix_type == "rotate":
            return 0.0
        return (0.0, 0.0)
