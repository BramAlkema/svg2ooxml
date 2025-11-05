"""Transform animation handler.

This module handles transform animations (scale, rotate, translate).
Generates PowerPoint <a:animScale>, <a:animRot>, or <a:animMotion> elements.
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
    """Handler for transform animations.

    Handles scale, rotate, translate, and reducible matrix animations.
    Generates PowerPoint transform animation elements based on transform type.

    Transform Types:
    - Scale: <a:animScale> with from/to <a:pt x="..." y="..."/>
    - Rotate: <a:animRot> with <a:by val="..."/> (rotation delta)
    - Translate: <a:animMotion> with origin/path
    - Matrix: decomposed into translate/scale/rotate when possible

    Example:
        >>> handler = TransformAnimationHandler(xml_builder, value_processor, tav_builder, unit_converter)
        >>> animation = Mock(transform_type="scale", values=["1", "2"], duration_ms=1000)
        >>> if handler.can_handle(animation):
        ...     xml = handler.build(animation, par_id=1, behavior_id=2)
    """

    def __init__(
        self,
        xml_builder: AnimationXMLBuilder,
        value_processor: ValueProcessor,
        tav_builder: TAVBuilder,
        unit_converter: UnitConverter,
    ):
        """Initialize transform animation handler.

        Args:
            xml_builder: XML builder for creating PowerPoint elements
            value_processor: Processor for normalizing animation values
            tav_builder: Builder for creating keyframe (TAV) lists
            unit_converter: Converter for SVG units to PowerPoint EMU
        """
        super().__init__(xml_builder, value_processor, tav_builder, unit_converter)

    def can_handle(self, animation: AnimationDefinition) -> bool:
        """Check if this handler can process the animation.

        Handles animations with transform_type attribute set to:
        - TransformType.SCALE
        - TransformType.ROTATE
        - TransformType.TRANSLATE
        - TransformType.MATRIX

        Args:
            animation: Animation definition to check

        Returns:
            True if animation has a supported transform_type

        Example:
            >>> handler.can_handle(animation)
            True  # if animation.transform_type == TransformType.SCALE
        """
        if not hasattr(animation, "transform_type") or animation.transform_type is None:
            return False

        # Import TransformType enum
        from svg2ooxml.ir.animation import TransformType

        # Check if it's a TransformType enum
        if isinstance(animation.transform_type, TransformType):
            return animation.transform_type in {
                TransformType.SCALE,
                TransformType.ROTATE,
                TransformType.TRANSLATE,
                TransformType.MATRIX,
            }

        # Also support string values for backward compatibility
        transform_str = str(animation.transform_type).lower()
        return transform_str in {"scale", "rotate", "translate", "matrix"}

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        """Build PowerPoint timing XML for transform animation.

        Dispatches to type-specific builder based on transform_type:
        - SCALE → _build_scale_animation
        - ROTATE → _build_rotate_animation
        - TRANSLATE → _build_translate_animation

        Args:
            animation: Animation definition to convert
            par_id: Unique ID for the <p:par> element
            behavior_id: Unique ID for the behavior element

        Returns:
            PowerPoint timing XML as string

        Example:
            >>> xml = handler.build(animation, par_id=1, behavior_id=2)
            >>> # Returns: '<p:par>...<a:animScale>...</a:animScale>...</p:par>'
        """
        if not hasattr(animation, "transform_type"):
            return ""

        # Import TransformType enum
        from svg2ooxml.ir.animation import TransformType

        # Get transform type (handle both enum and string)
        transform_type = animation.transform_type
        if isinstance(transform_type, TransformType):
            transform_type = transform_type.value

        # Dispatch based on type
        if transform_type == "scale":
            return self._build_scale_animation(animation, par_id, behavior_id)
        elif transform_type == "rotate":
            return self._build_rotate_animation(animation, par_id, behavior_id)
        elif transform_type == "translate":
            return self._build_translate_animation(animation, par_id, behavior_id)
        elif transform_type == "matrix":
            return self._build_matrix_animation(animation, par_id, behavior_id)

        return ""

    def _build_scale_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        """Build scale animation (<a:animScale>).

        Generates PowerPoint scale animation with from/to scale pairs.
        Scale values are points with x and y components.

        Args:
            animation: Animation definition
            par_id: Par container ID
            behavior_id: Behavior ID

        Returns:
            PowerPoint XML string

        Example:
            >>> xml = handler._build_scale_animation(animation, 1, 2)
            >>> # <a:animScale><a:from><a:pt x="1" y="1"/></a:from>...</a:animScale>
        """
        if not animation.values:
            return ""

        scale_pairs = [self._processor.parse_scale_pair(value) for value in animation.values]
        anim_scale = self._build_scale_from_pairs(animation, par_id, behavior_id, scale_pairs)
        if not anim_scale:
            return ""
        return self._xml.build_par_container(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_content=anim_scale,
        )

    def _build_rotate_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        """Build rotate animation (<a:animRot>).

        Generates PowerPoint rotate animation with rotation delta.
        Uses <a:by val="..."/> for rotation amount in PowerPoint angle units.

        Args:
            animation: Animation definition
            par_id: Par container ID
            behavior_id: Behavior ID

        Returns:
            PowerPoint XML string

        Example:
            >>> xml = handler._build_rotate_animation(animation, 1, 2)
            >>> # <a:animRot><a:by val="21600000"/></a:animRot>  (360 degrees)
        """
        if not animation.values:
            return ""

        angles = [self._processor.parse_angle(value) for value in animation.values]
        anim_rot = self._build_rotate_from_angles(animation, par_id, behavior_id, angles)
        if not anim_rot:
            return ""
        return self._xml.build_par_container(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_content=anim_rot,
        )

    def _build_translate_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        """Build translate animation (<a:animMotion>)."""
        if not animation.values:
            return ""

        translation_pairs = [
            self._processor.parse_translation_pair(value)
            for value in animation.values
        ]
        anim_motion = self._build_translate_from_pairs(animation, par_id, behavior_id, translation_pairs)
        if not anim_motion:
            return ""
        return self._xml.build_par_container(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_content=anim_motion,
        )

    def _build_matrix_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        """Build animation for matrix transforms when reducible to primitive components."""
        if not animation.values:
            return ""

        matrices: list[Matrix2D] = []
        for raw in animation.values:
            if isinstance(raw, str):
                tokens = [token for token in re.split(r"[,\s]+", raw.strip()) if token]
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
            # All identities → nothing to animate
            return ""

        classified: list[object] = []
        for current_type, payload in staged:
            if current_type == "identity":
                classified.append(self._identity_payload(matrix_type))
            else:
                classified.append(payload if payload is not None else self._identity_payload(matrix_type))

        content = ""
        if matrix_type == "translate":
            pairs = [(float(x), float(y)) for x, y in classified]  # type: ignore[arg-type]
            content = self._build_translate_from_pairs(animation, par_id, behavior_id, pairs)
        elif matrix_type == "scale":
            pairs = [(float(x), float(y)) for x, y in classified]  # type: ignore[arg-type]
            content = self._build_scale_from_pairs(animation, par_id, behavior_id, pairs)
        elif matrix_type == "rotate":
            angles = [float(angle) for angle in classified]  # type: ignore[arg-type]
            content = self._build_rotate_from_angles(animation, par_id, behavior_id, angles)

        if not content:
            return ""

        return self._xml.build_par_container(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_content=content,
        )

    def _build_scale_from_pairs(
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

        anim_tag = "<a:animScale"
        if needs_custom_ns:
            from ..constants import SVG2_ANIMATION_NS
            anim_tag += f' xmlns:svg2="{SVG2_ANIMATION_NS}"'
        anim_tag += ">"

        anim_scale = (
            f'                                    {anim_tag}\n'
            f'{behavior_core}'
            f'                                        <a:from>\n'
            f'                                            <a:pt x="{self._format_float(from_scale[0])}" y="{self._format_float(from_scale[1])}"/>\n'
            f'                                        </a:from>\n'
            f'                                        <a:to>\n'
            f'                                            <a:pt x="{self._format_float(to_scale[0])}" y="{self._format_float(to_scale[1])}"/>\n'
            f'                                        </a:to>\n'
            f'{tav_block}'
            f'                                    </a:animScale>'
        )

        return anim_scale

    def _build_scale_tav_list(
        self,
        animation: AnimationDefinition,
        scale_pairs: list[tuple[float, float]],
    ) -> tuple[list, bool]:
        """Build TAV list for multi-keyframe scale animations.

        Scale TAV values use point format with x/y scale factors.

        Args:
            animation: Animation definition
            scale_pairs: Sequence of (scale_x, scale_y) values

        Returns:
            Tuple of (tav_elements, needs_custom_namespace)
        """
        if not scale_pairs or (len(scale_pairs) <= 2 and not animation.key_times):
            return ([], False)

        # Format scale pairs as "x y" strings for point formatter
        scale_strings = [f"{x} {y}" for x, y in scale_pairs]

        # Build TAV list using point formatter
        tav_elements, needs_ns = self._tav.build_tav_list(
            values=scale_strings,
            key_times=animation.key_times,
            key_splines=animation.key_splines,
            duration_ms=animation.duration_ms,
            value_formatter=format_point_value,
        )

        return (tav_elements, needs_ns)

    def _build_rotate_from_angles(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        angles: list[float],
    ) -> str:
        if not angles:
            return ""

        start_angle = angles[0]
        end_angle = angles[-1]
        rotation_delta = self._processor.format_ppt_angle(end_angle - start_angle)

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

        anim_tag = "<a:animRot"
        if needs_custom_ns:
            from ..constants import SVG2_ANIMATION_NS
            anim_tag += f' xmlns:svg2="{SVG2_ANIMATION_NS}"'
        anim_tag += ">"

        anim_rot = (
            f'                                    {anim_tag}\n'
            f'{behavior_core}'
            f'                                        <a:by val="{rotation_delta}"/>\n'
            f'{tav_block}'
            f'                                    </a:animRot>'
        )

        return anim_rot

    def _build_rotate_tav_list(
        self,
        animation: AnimationDefinition,
        angles: list[float],
        start_angle: float,
    ) -> tuple[list, bool]:
        """Build TAV list for multi-keyframe rotate animations.

        Rotate TAV values are cumulative angles from start position.

        Args:
            animation: Animation definition
            angles: Sequence of angle values (degrees)
            start_angle: Starting angle in degrees

        Returns:
            Tuple of (tav_elements, needs_custom_namespace)
        """
        if not angles or (len(angles) <= 2 and not animation.key_times):
            return ([], False)

        # Convert to cumulative deltas from start (in degrees)
        angle_deltas = [str(angle - start_angle) for angle in angles]

        # Build TAV list using angle formatter
        tav_elements, needs_ns = self._tav.build_tav_list(
            values=angle_deltas,
            key_times=animation.key_times,
            key_splines=animation.key_splines,
            duration_ms=animation.duration_ms,
            value_formatter=format_angle_value,
        )

        return (tav_elements, needs_ns)

    def _build_translate_from_pairs(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        translation_pairs: list[tuple[float, float]],
    ) -> str:
        if len(translation_pairs) == 1:
            translation_pairs = [(0.0, 0.0), translation_pairs[0]]

        if len(translation_pairs) < 2:
            return ""

        behavior_core = self._xml.build_behavior_core(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id if hasattr(animation, "element_id") else "",
        )

        if len(translation_pairs) == 2:
            start_dx, start_dy = translation_pairs[0]
            end_dx, end_dy = translation_pairs[1]
            delta_x = int(round(self._units.to_emu(end_dx - start_dx, axis="x")))
            delta_y = int(round(self._units.to_emu(end_dy - start_dy, axis="y")))
            anim_motion = (
                f'                                    <a:animMotion>\n'
                f'{behavior_core}'
                f'                                        <a:by x="{delta_x}" y="{delta_y}"/>\n'
                f'                                    </a:animMotion>'
            )
        else:
            point_entries: list[str] = []
            for dx, dy in translation_pairs:
                x_emu = int(round(self._units.to_emu(dx, axis="x")))
                y_emu = int(round(self._units.to_emu(dy, axis="y")))
                point_entries.append(
                    f'                                        <a:pt x="{x_emu}" y="{y_emu}"/>'
                )

            pt_lst = "\n".join(point_entries)

            anim_motion = (
                f'                                    <a:animMotion>\n'
                f'{behavior_core}'
                f'                                        <a:ptLst>\n'
                f'{pt_lst}\n'
                f'                                        </a:ptLst>\n'
                f'                                    </a:animMotion>'
            )

        return anim_motion

    def _classify_matrix(
        self,
        matrix: Matrix2D,
        *,
        tolerance: float = 1e-6,
    ) -> tuple[str | None, object | None]:
        """Classify matrix as translate/scale/rotate when possible."""
        if (
            math.isfinite(matrix.a)
            and math.isfinite(matrix.b)
            and math.isfinite(matrix.c)
            and math.isfinite(matrix.d)
            and math.isfinite(matrix.e)
            and math.isfinite(matrix.f)
        ):
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

        return (None, None)

    @staticmethod
    def _identity_payload(matrix_type: str) -> object:
        if matrix_type == "translate":
            return (0.0, 0.0)
        if matrix_type == "scale":
            return (1.0, 1.0)
        if matrix_type == "rotate":
            return 0.0
        return (0.0, 0.0)

    def _format_float(self, value: float) -> str:
        """Format float value for XML output.

        Strips trailing zeros and decimal point for clean output.

        Args:
            value: Float value to format

        Returns:
            Formatted string

        Example:
            >>> handler._format_float(1.5)
            "1.5"
            >>> handler._format_float(2.0)
            "2"
        """
        formatted = f"{value:.6f}"
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")
        if not formatted:
            formatted = "0"
        if "." not in formatted:
            formatted = f"{formatted}.0"
        return formatted
