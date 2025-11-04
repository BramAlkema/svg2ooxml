"""Transform animation handler.

This module handles transform animations (scale, rotate, translate).
Generates PowerPoint <a:animScale>, <a:animRot>, or <a:animMotion> elements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import AnimationHandler, AnimationDefinition
from ..value_formatters import format_point_value, format_angle_value

if TYPE_CHECKING:
    from svg2ooxml.common.units import UnitConverter
    from ..tav_builder import TAVBuilder
    from ..value_processors import ValueProcessor
    from ..xml_builders import AnimationXMLBuilder

__all__ = ["TransformAnimationHandler"]


class TransformAnimationHandler(AnimationHandler):
    """Handler for transform animations.

    Handles scale, rotate, and translate animations.
    Generates PowerPoint transform animation elements based on transform type.

    Transform Types:
    - Scale: <a:animScale> with from/to <a:pt x="..." y="..."/>
    - Rotate: <a:animRot> with <a:by val="..."/> (rotation delta)
    - Translate: <a:animMotion> with origin/path (not yet implemented)

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
            }

        # Also support string values for backward compatibility
        transform_str = str(animation.transform_type).lower()
        return transform_str in {"scale", "rotate", "translate"}

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

        # Parse from/to scale pairs
        from_scale = self._processor.parse_scale_pair(animation.values[0])
        to_scale = self._processor.parse_scale_pair(animation.values[-1])

        # Build TAV list if multi-keyframe
        tav_elements, needs_custom_ns = self._build_scale_tav_list(animation)

        # Build behavior core
        behavior_core = self._xml.build_behavior_core(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id if hasattr(animation, "element_id") else "",
        )

        # Build TAV list container if needed
        tav_block = ""
        if tav_elements:
            tav_container = self._xml.build_tav_list_container(tav_elements)
            tav_block = (
                f'                                        <a:tavLst>\n'
                f'{tav_container}\n'
                f'                                        </a:tavLst>\n'
            )

        # Build animScale element
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

        # Build par container
        par = self._xml.build_par_container(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_content=anim_scale,
        )

        return par

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

        # Parse start/end angles
        start_angle = self._processor.parse_angle(animation.values[0])
        end_angle = self._processor.parse_angle(animation.values[-1])

        # Calculate rotation delta in PowerPoint units (60000ths of a degree)
        rotation_delta = self._processor.format_ppt_angle(end_angle - start_angle)

        # Build TAV list if multi-keyframe
        tav_elements, needs_custom_ns = self._build_rotate_tav_list(
            animation, start_angle
        )

        # Build behavior core
        behavior_core = self._xml.build_behavior_core(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id if hasattr(animation, "element_id") else "",
        )

        # Build TAV list container if needed
        tav_block = ""
        if tav_elements:
            tav_container = self._xml.build_tav_list_container(tav_elements)
            tav_block = (
                f'                                        <a:tavLst>\n'
                f'{tav_container}\n'
                f'                                        </a:tavLst>\n'
            )

        # Build animRot element
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

        # Build par container
        par = self._xml.build_par_container(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_content=anim_rot,
        )

        return par

    def _build_translate_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        """Build translate animation (<a:animMotion>).

        Note: Not yet fully implemented. Returns empty string.

        Args:
            animation: Animation definition
            par_id: Par container ID
            behavior_id: Behavior ID

        Returns:
            Empty string (not implemented)
        """
        # TODO: Implement translate animation
        # Would use <a:animMotion> with origin and path
        return ""

    def _build_scale_tav_list(
        self,
        animation: AnimationDefinition,
    ) -> tuple[list, bool]:
        """Build TAV list for multi-keyframe scale animations.

        Scale TAV values use point format with x/y scale factors.

        Args:
            animation: Animation definition

        Returns:
            Tuple of (tav_elements, needs_custom_namespace)
        """
        values = animation.values
        if not values or (len(values) <= 2 and not animation.key_times):
            return ([], False)

        # Parse all scale pairs
        scale_pairs = [self._processor.parse_scale_pair(val) for val in values]

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

    def _build_rotate_tav_list(
        self,
        animation: AnimationDefinition,
        start_angle: float,
    ) -> tuple[list, bool]:
        """Build TAV list for multi-keyframe rotate animations.

        Rotate TAV values are cumulative angles from start position.

        Args:
            animation: Animation definition
            start_angle: Starting angle in degrees

        Returns:
            Tuple of (tav_elements, needs_custom_namespace)
        """
        values = animation.values
        if not values or (len(values) <= 2 and not animation.key_times):
            return ([], False)

        # Parse all angles
        angles = [self._processor.parse_angle(val) for val in values]

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
        return formatted or "0"
