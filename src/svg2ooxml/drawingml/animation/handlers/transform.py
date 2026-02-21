"""Transform animation handler.

Generates PowerPoint ``<p:animScale>``, ``<p:animRot>``, or ``<p:animMotion>``
elements for ``<animateTransform>`` animations (scale, rotate, translate, matrix).
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.common.conversions.scale import scale_to_ppt
from svg2ooxml.drawingml.xml_builder import p_elem, p_sub
from svg2ooxml.ir.animation import TransformType

from .base import AnimationHandler

if TYPE_CHECKING:
    from svg2ooxml.common.geometry.matrix import Matrix2D
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = ["TransformAnimationHandler"]


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
            child = self._build_scale_element(animation, behavior_id, scale_pairs)
            preset_class = "emph"
            preset_id = 6  # Grow/Shrink
        elif transform_type == TransformType.ROTATE:
            angles = [self._processor.parse_angle(v) for v in animation.values]
            child = self._build_rotate_element(animation, behavior_id, angles)
            preset_class = "emph"
            preset_id = 8  # Spin
        elif transform_type == TransformType.TRANSLATE:
            translation_pairs = [
                self._processor.parse_translation_pair(v) for v in animation.values
            ]
            child = self._build_translate_element(animation, behavior_id, translation_pairs)
            preset_class = "path"
            preset_id = 0  # Custom Path
        elif transform_type == TransformType.MATRIX:
            child, preset_class = self._build_matrix_element(animation, behavior_id)
        else:
            return None

        if child is None:
            return None

        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=child,
            preset_id=preset_id,
            preset_class=preset_class,
            preset_subtype=None,
            node_type="withEffect",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
        )

    # ------------------------------------------------------------------ #
    # Scale                                                                #
    # ------------------------------------------------------------------ #

    def _build_scale_element(
        self,
        animation: AnimationDefinition,
        behavior_id: int,
        scale_pairs: list[tuple[float, float]],
    ) -> etree._Element | None:
        if not scale_pairs:
            return None

        from_sx, from_sy = scale_pairs[0]
        to_sx, to_sy = scale_pairs[-1]

        anim_scale = p_elem("animScale")

        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim_scale.append(cBhvr)

        p_sub(
            anim_scale, "from",
            x=str(scale_to_ppt(from_sx)),
            y=str(scale_to_ppt(from_sy)),
        )
        p_sub(
            anim_scale, "to",
            x=str(scale_to_ppt(to_sx)),
            y=str(scale_to_ppt(to_sy)),
        )

        return anim_scale

    # ------------------------------------------------------------------ #
    # Rotate                                                               #
    # ------------------------------------------------------------------ #

    def _build_rotate_element(
        self,
        animation: AnimationDefinition,
        behavior_id: int,
        angles: list[float],
    ) -> etree._Element | None:
        if not angles:
            return None

        start_angle = angles[0]
        rotation_delta = self._processor.format_ppt_angle(angles[-1] - start_angle)

        anim_rot = p_elem("animRot", by=rotation_delta)

        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim_rot.append(cBhvr)

        return anim_rot

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

        # Multi-keyframe: build a motion path with M/L segments
        if len(translation_pairs) > 2:
            return self._build_translate_path_element(
                animation, behavior_id, translation_pairs,
            )

        # Simple 2-value: use <p:by> delta
        start_dx, start_dy = translation_pairs[0]
        end_dx, end_dy = translation_pairs[-1]

        delta_x = int(round(self._units.to_emu(end_dx - start_dx, axis="x")))
        delta_y = int(round(self._units.to_emu(end_dy - start_dy, axis="y")))

        anim_motion = p_elem("animMotion")

        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim_motion.append(cBhvr)

        p_sub(anim_motion, "by", x=str(delta_x), y=str(delta_y))
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
        from svg2ooxml.drawingml.writer import DEFAULT_SLIDE_SIZE

        slide_w, slide_h = DEFAULT_SLIDE_SIZE
        start_x, start_y = translation_pairs[0]

        # Build M/L path string in slide-fraction coordinates
        segments: list[str] = []
        for i, (x_px, y_px) in enumerate(translation_pairs):
            dx_px = x_px - start_x
            dy_px = y_px - start_y

            dx_emu = self._units.to_emu(dx_px, axis="x")
            dy_emu = self._units.to_emu(dy_px, axis="y")

            nx = dx_emu / slide_w
            ny = dy_emu / slide_h

            cmd = "M" if i == 0 else "L"
            segments.append(f"{cmd} {self._format_coord(nx)} {self._format_coord(ny)}")

        path = " ".join(segments) + " E"
        pts_types = "A" * len(translation_pairs)

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
    def _format_coord(value: float) -> str:
        """Format normalised coordinate as a string."""
        if abs(value) < 1e-10:
            return "0"
        return f"{value:.6g}"

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
                    payload if payload is not None else self._identity_payload(matrix_type)
                )

        if matrix_type == "translate":
            pairs = [(float(x), float(y)) for x, y in classified]
            return self._build_translate_element(animation, behavior_id, pairs), "path"
        elif matrix_type == "scale":
            pairs = [(float(x), float(y)) for x, y in classified]
            return self._build_scale_element(animation, behavior_id, pairs), "entr"
        elif matrix_type == "rotate":
            angles = [float(angle) for angle in classified]
            return self._build_rotate_element(animation, behavior_id, angles), "entr"

        return None, "entr"

    # ------------------------------------------------------------------ #
    # Matrix classification                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _classify_matrix(
        matrix: Matrix2D, *, tolerance: float = 1e-6
    ) -> tuple[str | None, object | None]:
        if not all(
            math.isfinite(v) for v in (matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f)
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
        decomposed = TransformAnimationHandler._decompose_matrix(matrix, tolerance=tolerance)
        if decomposed is not None:
            return decomposed

        return (None, None)

    @staticmethod
    def _decompose_matrix(
        matrix: Matrix2D, *, tolerance: float = 1e-6,
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
        sx = math.sqrt(matrix.a ** 2 + matrix.b ** 2)
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

        if abs(matrix.c - expected_c) > tolerance or abs(matrix.d - expected_d) > tolerance:
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
