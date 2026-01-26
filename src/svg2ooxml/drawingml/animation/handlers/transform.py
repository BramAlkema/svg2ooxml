"""Transform animation handler.

This module handles transform animations (scale, rotate, translate).
Generates PowerPoint <p:animScale>, <p:animRot>, or <p:animMotion> elements.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING
from textwrap import indent

from lxml import etree

from .base import AnimationHandler, AnimationDefinition
from ..value_formatters import format_point_value, format_angle_value
from ..constants import SVG2_ANIMATION_NS
from svg2ooxml.common.geometry.matrix import Matrix2D
from svg2ooxml.drawingml.xml_builder import to_string

etree.register_namespace("svg2", SVG2_ANIMATION_NS)

if TYPE_CHECKING:
    from svg2ooxml.common.units import UnitConverter
    from ..tav_builder import TAVBuilder
    from ..value_processors import ValueProcessor
    from ..xml_builders import AnimationXMLBuilder

__all__ = ["TransformAnimationHandler"]


class TransformAnimationHandler(AnimationHandler):
    """Handler for transform animations."""

    def __init__(
        self,
        xml_builder: AnimationXMLBuilder,
        value_processor: ValueProcessor,
        tav_builder: TAVBuilder,
        unit_converter: UnitConverter,
    ):
        super().__init__(xml_builder, value_processor, tav_builder, unit_converter)

    def can_handle(self, animation: AnimationDefinition) -> bool:
        if not hasattr(animation, "transform_type") or animation.transform_type is None:
            return False

        from svg2ooxml.ir.animation import TransformType

        if isinstance(animation.transform_type, TransformType):
            return animation.transform_type in {
                TransformType.SCALE,
                TransformType.ROTATE,
                TransformType.TRANSLATE,
                TransformType.MATRIX,
            }

        transform_str = str(animation.transform_type).lower()
        return transform_str in {"scale", "rotate", "translate", "matrix"}

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        if not hasattr(animation, "transform_type"):
            return ""

        from svg2ooxml.ir.animation import TransformType
        transform_type = animation.transform_type
        if isinstance(transform_type, TransformType):
            transform_type = transform_type.value

        content = ""
        preset_id = 0
        preset_class = "entr"
        preset_subtype = 0

        # Dispatch based on type
        if transform_type == "scale":
            scale_pairs = [self._processor.parse_scale_pair(value) for value in animation.values]
            content = self._build_scale_behavior_content(animation, par_id, behavior_id, scale_pairs)
        elif transform_type == "rotate":
            angles = [self._processor.parse_angle(value) for value in animation.values]
            content = self._build_rotate_behavior_content(animation, par_id, behavior_id, angles)
        elif transform_type == "translate":
            translation_pairs = [self._processor.parse_translation_pair(value) for value in animation.values]
            content = self._build_translate_behavior_content(animation, par_id, behavior_id, translation_pairs)
            preset_class = "path"
        elif transform_type == "matrix":
            content = self._build_matrix_behavior_content(animation, par_id, behavior_id)

        if not content:
            return ""

        return self._xml.build_par_container(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_content=content,
            preset_id=preset_id,
            preset_class=preset_class,
            preset_subtype=preset_subtype,
            node_type="withEffect",
        )

    def _build_matrix_behavior_content(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        if not animation.values:
            return ""

        matrices: list[Matrix2D] = []
        for raw in animation.values:
            if isinstance(raw, str):
                tokens = [token for token in re.split(r"[\s,]+", raw.strip()) if token]
            else:
                return ""
            if len(tokens) < 6:
                return ""
            try:
                values = [float(token) for token in tokens[:6]]
            except ValueError:
                return ""
            matrices.append(Matrix2D.from_values(*values))

        matrix_type: str | None = None
        staged: list[tuple[str, object | None]] = []

        for matrix in matrices:
            current_type, payload = self._classify_matrix(matrix)
            if current_type is None:
                return ""

            if matrix_type is None:
                if current_type != "identity":
                    matrix_type = current_type
            else:
                if current_type not in {"identity", matrix_type}:
                    return ""

            staged.append((current_type, payload))

        if matrix_type is None:
            return ""

        classified: list[object] = []
        for current_type, payload in staged:
            if current_type == "identity":
                classified.append(self._identity_payload(matrix_type))
            else:
                classified.append(payload if payload is not None else self._identity_payload(matrix_type))

        if matrix_type == "translate":
            pairs = [(float(x), float(y)) for x, y in classified]
            return self._build_translate_behavior_content(animation, par_id, behavior_id, pairs)
        elif matrix_type == "scale":
            pairs = [(float(x), float(y)) for x, y in classified]
            return self._build_scale_behavior_content(animation, par_id, behavior_id, pairs)
        elif matrix_type == "rotate":
            angles = [float(angle) for angle in classified]
            return self._build_rotate_behavior_content(animation, par_id, behavior_id, angles)

        return ""

    def _build_scale_behavior_content(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        scale_pairs: list[tuple[float, float]],
    ) -> str:
        if not scale_pairs:
            return ""

        from_scale = scale_pairs[0]
        to_scale = scale_pairs[-1]

        tav_elements, needs_custom_ns = self._build_scale_tav_list(animation, scale_pairs)

        behavior_core = self._xml.build_behavior_core(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id if hasattr(animation, "element_id") else "",
        )

        tav_block = ""
        if tav_elements:
            tav_container = self._xml.build_tav_list_container(tav_elements)
            tav_string = to_string(tav_container)
            tav_block = "\n" + indent(tav_string, " " * 40) + "\n"

        anim_tag = "<p:animScale"
        if needs_custom_ns:
            from ..constants import SVG2_ANIMATION_NS
            anim_tag += f' xmlns:svg2="{SVG2_ANIMATION_NS}"'
        anim_tag += ">"

        return (
            f'                                    {anim_tag}\n'
            f'{behavior_core}'
            f'                                        <p:from x="{int(round(from_scale[0] * 100000))}" y="{int(round(from_scale[1] * 100000))}"/>\n'
            f'                                        <p:to x="{int(round(to_scale[0] * 100000))}" y="{int(round(to_scale[1] * 100000))}"/>\n'
            f'{tav_block}'
            f'                                    </p:animScale>'
        )

    def _build_rotate_behavior_content(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        angles: list[float],
    ) -> str:
        if not angles:
            return ""

        start_angle = angles[0]
        rotation_delta = self._processor.format_ppt_angle(angles[-1] - start_angle)

        tav_elements, needs_custom_ns = self._build_rotate_tav_list(animation, angles, start_angle)

        behavior_core = self._xml.build_behavior_core(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id if hasattr(animation, "element_id") else "",
        )

        tav_block = ""
        if tav_elements:
            tav_container = self._xml.build_tav_list_container(tav_elements)
            tav_string = to_string(tav_container)
            tav_block = "\n" + indent(tav_string, " " * 40) + "\n"

        anim_tag = "<p:animRot"
        if needs_custom_ns:
            from ..constants import SVG2_ANIMATION_NS
            anim_tag += f' xmlns:svg2="{SVG2_ANIMATION_NS}"'
        anim_tag += f' by="{rotation_delta}"'
        anim_tag += ">"

        return (
            f'                                    {anim_tag}\n'
            f'{behavior_core}'
            f'{tav_block}'
            f'                                    </p:animRot>'
        )

    def _build_translate_behavior_content(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        translation_pairs: list[tuple[float, float]],
    ) -> str:
        if len(translation_pairs) < 2:
            return ""

        # Always take the first and last point for a 'by' animation
        start_dx, start_dy = translation_pairs[0]
        end_dx, end_dy = translation_pairs[-1] # Use the last point

        delta_x = int(round(self._units.to_emu(end_dx - start_dx, axis="x")))
        delta_y = int(round(self._units.to_emu(end_dy - start_dy, axis="y")))

        return (
            f'                                    <p:animMotion>\n'
            f'{behavior_core}'
            f'                                        <p:by x="{delta_x}" y="{delta_y}"/>\n'
            f'                                    </p:animMotion>'
        )

    def _build_scale_tav_list(self, animation, scale_pairs) -> tuple[list, bool]:
        if not scale_pairs or (len(scale_pairs) <= 2 and not animation.key_times):
            return ([], False)
        scale_strings = [f"{x * 100000} {y * 100000}" for x, y in scale_pairs]
        return self._tav.build_tav_list(
            values=scale_strings,
            key_times=animation.key_times,
            key_splines=animation.key_splines,
            duration_ms=animation.duration_ms,
            value_formatter=format_point_value,
        )

    def _build_rotate_tav_list(self, animation, angles, start_angle) -> tuple[list, bool]:
        if not angles or (len(angles) <= 2 and not animation.key_times):
            return ([], False)
        angle_deltas = [str(angle - start_angle) for angle in angles]
        return self._tav.build_tav_list(
            values=angle_deltas,
            key_times=animation.key_times,
            key_splines=animation.key_splines,
            duration_ms=animation.duration_ms,
            value_formatter=format_angle_value,
        )

    def _classify_matrix(self, matrix: Matrix2D, *, tolerance: float = 1e-6) -> tuple[str | None, object | None]:
        if (
            math.isfinite(matrix.a) and math.isfinite(matrix.b) and 
            math.isfinite(matrix.c) and math.isfinite(matrix.d) and 
            math.isfinite(matrix.e) and math.isfinite(matrix.f)
        ):
            if (
                abs(matrix.a - 1.0) <= tolerance and abs(matrix.d - 1.0) <= tolerance and 
                abs(matrix.b) <= tolerance and abs(matrix.c) <= tolerance and 
                abs(matrix.e) <= tolerance and abs(matrix.f) <= tolerance
            ):
                return ("identity", None)
            if (
                abs(matrix.a - 1.0) <= tolerance and abs(matrix.d - 1.0) <= tolerance and 
                abs(matrix.b) <= tolerance and abs(matrix.c) <= tolerance
            ):
                return ("translate", (matrix.e, matrix.f))
            if (
                abs(matrix.b) <= tolerance and abs(matrix.c) <= tolerance and 
                abs(matrix.e) <= tolerance and abs(matrix.f) <= tolerance
            ):
                return ("scale", (matrix.a, matrix.d))
            if (
                abs(matrix.e) <= tolerance and abs(matrix.f) <= tolerance and 
                abs(matrix.c + matrix.b) <= tolerance and abs(matrix.a - matrix.d) <= tolerance and 
                abs(matrix.a * matrix.a + matrix.b * matrix.b - 1.0) <= tolerance and 
                abs(matrix.c * matrix.c + matrix.d * matrix.d - 1.0) <= tolerance
            ):
                angle_deg = math.degrees(math.atan2(matrix.b, matrix.a))
                return ("rotate", angle_deg)
        return (None, None)

    @staticmethod
    def _identity_payload(matrix_type: str) -> object:
        if matrix_type == "translate": return (0.0, 0.0)
        if matrix_type == "scale": return (1.0, 1.0)
        if matrix_type == "rotate": return 0.0
        return (0.0, 0.0)

    def _format_float(self, value: float) -> str:
        formatted = f"{value:.6f}"
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")
        if not formatted: formatted = "0"
        if "." not in formatted: formatted = f"{formatted}.0"
        return formatted