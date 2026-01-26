"""Opacity animation handler.

This module handles opacity/fade animations (opacity, fill-opacity, stroke-opacity).
Generates PowerPoint <a:animEffect> with <a:fade> filter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import AnimationHandler, AnimationDefinition
from ..constants import FADE_ATTRIBUTES

if TYPE_CHECKING:
    from svg2ooxml.common.units import UnitConverter
    from ..tav_builder import TAVBuilder
    from ..value_processors import ValueProcessor
    from ..xml_builders import AnimationXMLBuilder

__all__ = ["OpacityAnimationHandler"]


class OpacityAnimationHandler(AnimationHandler):
    """Handler for opacity/fade animations.

    Handles animations on opacity, fill-opacity, and stroke-opacity attributes.
    Generates PowerPoint <a:animEffect> with <a:fade> filter.

    PowerPoint opacity animations use a simple in/out transition model:
    - transition in="1" out="0" means fade in (0 → 1)
    - Final opacity value comes from animation values

    Example:
        >>> handler = OpacityAnimationHandler(xml_builder, value_processor, tav_builder, unit_converter)
        >>> animation = Mock(attribute_name="opacity", values=["0", "1"], duration_ms=1000)
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
        """Initialize opacity animation handler.

        Args:
            xml_builder: XML builder for creating PowerPoint elements
            value_processor: Processor for normalizing animation values
            tav_builder: Builder for creating keyframe (TAV) lists
            unit_converter: Converter for SVG units to PowerPoint EMU
        """
        super().__init__(xml_builder, value_processor, tav_builder, unit_converter)

    def can_handle(self, animation: AnimationDefinition) -> bool:
        """Check if this handler can process the animation.

        Handles animations on fade attributes: opacity, fill-opacity, stroke-opacity.
        Only processes ANIMATE type (not ANIMATE_MOTION, ANIMATE_TRANSFORM, etc.)

        Args:
            animation: Animation definition to check

        Returns:
            True if attribute_name is a fade attribute and animation_type is ANIMATE

        Example:
            >>> handler.can_handle(animation)
            True  # if animation.target_attribute == "opacity" and type is ANIMATE
        """
        # Import AnimationType enum
        from svg2ooxml.ir.animation import AnimationType

        # Only handle ANIMATE type animations (not ANIMATE_MOTION, ANIMATE_TRANSFORM, SET, etc.)
        animation_type = self._resolve_animation_type(animation)
        if animation_type is not None:
            if isinstance(animation_type, AnimationType):
                if animation_type != AnimationType.ANIMATE:
                    return False
            else:
                # String comparison for backward compatibility
                anim_type_str = self._animation_type_to_str(animation_type)
                if anim_type_str != "ANIMATE":
                    return False
        # If no animation_type, default to handling it (for backward compatibility)

        target_attribute = self._resolve_target_attribute(animation)
        if target_attribute is None:
            return False
        return target_attribute in FADE_ATTRIBUTES

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        """Build PowerPoint timing XML for opacity animation.

        Generates <p:par> container with <a:animEffect> and <a:fade> filter.
        The fade effect uses PowerPoint's in/out transition model with the
        target opacity value.

        Args:
            animation: Animation definition to convert
            par_id: Unique ID for the <p:par> element
            behavior_id: Unique ID for the behavior element

        Returns:
            PowerPoint timing XML as string

        Example:
            >>> xml = handler.build(animation, par_id=1, behavior_id=2)
            >>> # Returns: '<p:par>...<a:animEffect>...<a:fade opacity="1"/></a:animEffect>...</p:par>'
        """
        # Extract target opacity value
        target_opacity = self._compute_target_opacity(animation)

        # Build behavior core (common timing/target structure)
        behavior_core = self._xml.build_behavior_core(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id if hasattr(animation, "element_id") else "",
        )

        # Build animEffect element with fade filter
        anim_effect = (
            f'                                    <p:animEffect>\n'
            f'{behavior_core}'
            f'                                        <p:transition in="1" out="0"/>\n'
            f'                                        <p:filter>\n'
            f'                                            <p:fade opacity="{target_opacity}"/>\n'
            f'                                        </p:filter>\n'
            f'                                    </p:animEffect>'
        )

        # Build par container
        par = self._xml.build_par_container(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_content=anim_effect,
            preset_id=1,
            preset_class="entr",
            preset_subtype=0,
            node_type="withEffect",
        )

        return par

    def _compute_target_opacity(self, animation: AnimationDefinition) -> str:
        """Compute target opacity value for fade effect.

        PowerPoint fade effects use the final animation value as the target.
        If no values are provided, defaults based on fill mode.

        Args:
            animation: Animation definition

        Returns:
            Opacity value as string (e.g., "1", "0.5")

        Example:
            >>> handler._compute_target_opacity(animation)
            "1"  # If animation.values = ["0", "1"]
        """
        if animation.values:
            target_value = animation.values[-1]
            parsed = self._processor.parse_opacity(target_value)
            return str(parsed)

        # No values: default based on fill mode
        # freeze → end at visible (1), remove → end at invisible (0)
        default_value = "1" if animation.fill_mode == "freeze" else "0"
        return self._processor.parse_opacity(default_value)
