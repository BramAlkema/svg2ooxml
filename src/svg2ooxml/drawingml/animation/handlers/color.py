"""Color animation handler.

This module handles color animations (fill, stroke, stop-color, etc.).
Generates PowerPoint <a:animClr> with from/to color values and optional keyframes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from textwrap import indent

from .base import AnimationHandler, AnimationDefinition
from ..constants import COLOR_ATTRIBUTES, COLOR_ATTRIBUTE_NAME_MAP
from ..value_formatters import format_color_value
from svg2ooxml.drawingml.xml_builder import to_string

if TYPE_CHECKING:
    from svg2ooxml.common.units import UnitConverter
    from ..tav_builder import TAVBuilder
    from ..value_processors import ValueProcessor
    from ..xml_builders import AnimationXMLBuilder

__all__ = ["ColorAnimationHandler"]


class ColorAnimationHandler(AnimationHandler):
    """Handler for color animations.

    Handles animations on color attributes: fill, stroke, stop-color, flood-color, lighting-color.
    Generates PowerPoint <a:animClr> with from/to colors and optional TAV keyframes.

    PowerPoint color animations use:
    - <a:from><a:srgbClr val="..."/></a:from> for starting color
    - <a:to><a:srgbClr val="..."/></a:to> for ending color
    - Optional <a:tavLst> for multi-keyframe animations

    Example:
        >>> handler = ColorAnimationHandler(xml_builder, value_processor, tav_builder, unit_converter)
        >>> animation = Mock(attribute_name="fill", values=["#FF0000", "#00FF00"], duration_ms=1000)
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
        """Initialize color animation handler.

        Args:
            xml_builder: XML builder for creating PowerPoint elements
            value_processor: Processor for normalizing animation values
            tav_builder: Builder for creating keyframe (TAV) lists
            unit_converter: Converter for SVG units to PowerPoint EMU
        """
        super().__init__(xml_builder, value_processor, tav_builder, unit_converter)

    def can_handle(self, animation: AnimationDefinition) -> bool:
        """Check if this handler can process the animation.

        Handles animations on color attributes: fill, stroke, stop-color, etc.
        Only processes ANIMATE or ANIMATE_COLOR types.

        Args:
            animation: Animation definition to check

        Returns:
            True if attribute_name is a color attribute and type is ANIMATE/ANIMATE_COLOR

        Example:
            >>> handler.can_handle(animation)
            True  # if animation.target_attribute == "fill" and type is ANIMATE
        """
        # Import AnimationType enum
        from svg2ooxml.ir.animation import AnimationType

        # Only handle ANIMATE or ANIMATE_COLOR type animations
        animation_type = self._resolve_animation_type(animation)
        if animation_type is not None:
            if isinstance(animation_type, AnimationType):
                if animation_type not in {AnimationType.ANIMATE, AnimationType.ANIMATE_COLOR}:
                    return False
            else:
                # String comparison for backward compatibility
                anim_type_str = self._animation_type_to_str(animation_type)
                if anim_type_str not in {"ANIMATE", "ANIMATE_COLOR", "ANIMATECOLOR"}:
                    return False
        # If no animation_type, default to handling it (for backward compatibility)

        target_attribute = self._resolve_target_attribute(animation)
        if target_attribute is None:
            return False
        return target_attribute in COLOR_ATTRIBUTES

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        """Build PowerPoint timing XML for color animation.

        Generates <p:par> container with <a:animClr> element containing:
        - <a:cBhvr> with attribute name list
        - <a:from> with starting color
        - <a:to> with ending color
        - Optional <a:tavLst> for multi-keyframe animations

        Args:
            animation: Animation definition to convert
            par_id: Unique ID for the <p:par> element
            behavior_id: Unique ID for the behavior element

        Returns:
            PowerPoint timing XML as string

        Example:
            >>> xml = handler.build(animation, par_id=1, behavior_id=2)
            >>> # Returns: '<p:par>...<a:animClr>...<a:from>...<a:to>...</a:animClr>...</p:par>'
        """
        # Extract from/to colors
        if not animation.values:
            return ""

        from_color = self._processor.parse_color(animation.values[0])
        to_color = self._processor.parse_color(animation.values[-1])

        # Map attribute name to PowerPoint color attribute
        target_attribute = self._resolve_target_attribute(animation) or ""
        ppt_attribute = self._map_color_attribute(target_attribute)

        # Build TAV list if multi-keyframe
        tav_elements, needs_custom_ns = self._build_color_tav_list(animation)

        # Build attribute name list
        attr_list = self._xml.build_attribute_list([ppt_attribute])

        # Build behavior core with attribute list
        behavior_core = self._xml.build_behavior_core(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id if hasattr(animation, "element_id") else "",
            attribute_list=attr_list,
        )

        # Build TAV list container if needed
        tav_block = ""
        if tav_elements:
            tav_container = self._xml.build_tav_list_container(tav_elements)
            tav_string = to_string(tav_container)
            tav_block = "\n" + indent(tav_string, " " * 40) + "\n"

        # Build animClr element
        anim_tag = "<p:animClr"
        if needs_custom_ns:
            from ..constants import SVG2_ANIMATION_NS
            anim_tag += f' xmlns:svg2="{SVG2_ANIMATION_NS}"'
        anim_tag += ">"

        anim_clr = (
            f'                                    {anim_tag}\n'
            f'{behavior_core}'
            f'                                        <p:from>\n'
            f'                                            <p:val>\n'
            f'                                                <p:clr>\n'
            f'                                                    <p:srgbClr val="{from_color}"/>\n'
            f'                                                </p:clr>\n'
            f'                                            </p:val>\n'
            f'                                        </p:from>\n'
            f'                                        <p:to>\n'
            f'                                            <p:val>\n'
            f'                                                <p:clr>\n'
            f'                                                    <p:srgbClr val="{to_color}"/>\n'
            f'                                                </p:clr>\n'
            f'                                            </p:val>\n'
            f'                                        </p:to>\n'
            f'{tav_block}'
            f'                                    </p:animClr>'
        )

        # Build par container
        par = self._xml.build_par_container(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_content=anim_clr,
            preset_id=0,
            preset_class="entr",
            preset_subtype=0,
            node_type="withEffect",
        )

        return par

    def _map_color_attribute(self, attribute: str) -> str:
        """Map SVG color attribute to PowerPoint attribute name.

        Args:
            attribute: SVG attribute name (e.g., "fill", "stroke")

        Returns:
            PowerPoint attribute name (e.g., "fillClr", "lnClr")

        Example:
            >>> handler._map_color_attribute("fill")
            "fillClr"
            >>> handler._map_color_attribute("stroke")
            "lnClr"
        """
        return COLOR_ATTRIBUTE_NAME_MAP.get(attribute, "fillClr")

    def _build_color_tav_list(
        self,
        animation: AnimationDefinition,
    ) -> tuple[list, bool]:
        """Build TAV list for multi-keyframe color animations.

        Only builds TAV list if:
        - More than 2 values, OR
        - Explicit key_times provided

        Args:
            animation: Animation definition

        Returns:
            Tuple of (tav_elements, needs_custom_namespace)

        Example:
            >>> elements, needs_ns = handler._build_color_tav_list(animation)
            >>> # Returns: ([<tav1>, <tav2>, ...], True) if keyframes exist
        """
        values = animation.values
        if not values or (len(values) <= 2 and not animation.key_times):
            return ([], False)

        # Build TAV list using tav_builder
        tav_elements, needs_ns = self._tav.build_tav_list(
            values=values,
            key_times=animation.key_times,
            key_splines=animation.key_splines,
            duration_ms=animation.duration_ms,
            value_formatter=format_color_value,
        )

        return (tav_elements, needs_ns)
