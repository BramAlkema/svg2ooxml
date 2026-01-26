"""Set animation handler.

This module handles set animations (discrete attribute changes).
Generates PowerPoint <a:set> elements that set attributes to specific values.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import AnimationHandler, AnimationDefinition
from ..constants import COLOR_ATTRIBUTES, ATTRIBUTE_NAME_MAP, COLOR_ATTRIBUTE_NAME_MAP

if TYPE_CHECKING:
    from svg2ooxml.common.units import UnitConverter
    from ..tav_builder import TAVBuilder
    from ..value_processors import ValueProcessor
    from ..xml_builders import AnimationXMLBuilder

__all__ = ["SetAnimationHandler"]


class SetAnimationHandler(AnimationHandler):
    """Handler for set animations.

    Handles discrete set animations that change attributes to specific values.
    Generates PowerPoint <a:set> elements with attribute targets.

    Set animations are instantaneous changes (typically duration=1ms) that
    set an attribute to a specific value at a given time.

    PowerPoint set animations use:
    - <a:set> element
    - <a:cBhvr> with attribute name list
    - <a:to> with target value (either <a:val> for numeric or <a:srgbClr> for colors)

    Example:
        >>> handler = SetAnimationHandler(xml_builder, value_processor, tav_builder, unit_converter)
        >>> animation = Mock(animation_type="SET", attribute_name="visibility", values=["visible"], duration_ms=1)
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
        """Initialize set animation handler.

        Args:
            xml_builder: XML builder for creating PowerPoint elements
            value_processor: Processor for normalizing animation values
            tav_builder: Builder for creating keyframe (TAV) lists (not used for set)
            unit_converter: Converter for SVG units to PowerPoint EMU
        """
        super().__init__(xml_builder, value_processor, tav_builder, unit_converter)

    def can_handle(self, animation: AnimationDefinition) -> bool:
        """Check if this handler can process the animation.

        Handles animations with animation_type set to "SET" or "set".

        Args:
            animation: Animation definition to check

        Returns:
            True if animation is a set animation

        Example:
            >>> handler.can_handle(animation)
            True  # if animation.animation_type == "SET"
        """
        animation_type = self._resolve_animation_type(animation)
        if animation_type is None:
            return False

        anim_type_str = self._animation_type_to_str(animation_type)
        canonical_token = anim_type_str
        for delimiter in (".", ":"):
            if delimiter in canonical_token:
                canonical_token = canonical_token.split(delimiter)[-1]
        canonical_token = canonical_token.replace("-", "_")
        return canonical_token == "SET"

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        """Build PowerPoint timing XML for set animation.

        Generates <p:par> container with <a:set> element containing:
        - <a:cBhvr> with attribute name and target
        - <a:to> with target value

        Args:
            animation: Animation definition to convert
            par_id: Unique ID for the <p:par> element
            behavior_id: Unique ID for the behavior element

        Returns:
            PowerPoint timing XML as string

        Example:
            >>> xml = handler.build(animation, par_id=1, behavior_id=2)
            >>> # Returns: '<p:par>...<a:set>...<a:to>...</a:to>...</a:set>...</p:par>'
        """
        # Get the target value (last value in list)
        if not animation.values:
            return ""

        target_value = animation.values[-1]

        # Map attribute name to PowerPoint attribute
        target_attribute = self._resolve_target_attribute(animation) or ""
        ppt_attribute = self._map_attribute_name(target_attribute)

        # Determine if this is a color or numeric attribute
        is_color = target_attribute in COLOR_ATTRIBUTES

        # Build value block based on type
        if is_color:
            value_block = self._build_color_value_block(target_value)
        else:
            value_block = self._build_numeric_value_block(ppt_attribute, target_value)

        # Build attribute name list
        attr_list = self._xml.build_attribute_list([ppt_attribute])

        # Build behavior core with attribute list
        behavior_core = self._xml.build_behavior_core(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id if hasattr(animation, "element_id") else "",
            attribute_list=attr_list,
        )

        # Build set element
        anim_set = (
            f'                                    <p:set>\n'
            f'{behavior_core}'
            f'{value_block}'
            f'                                    </p:set>'
        )

        # Build par container
        par = self._xml.build_par_container(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_content=anim_set,
            preset_id=1,
            preset_class="entr",
            preset_subtype=0,
            node_type="withEffect",
        )

        return par

    def _map_attribute_name(self, attribute: str) -> str:
        """Map SVG attribute name to PowerPoint attribute name.

        Uses COLOR_ATTRIBUTE_NAME_MAP for color attributes, otherwise ATTRIBUTE_NAME_MAP.

        Args:
            attribute: SVG attribute name (e.g., "x", "fill", "visibility")

        Returns:
            PowerPoint attribute name (e.g., "ppt_x", "fillClr", "visibility")

        Example:
            >>> handler._map_attribute_name("x")
            "ppt_x"
            >>> handler._map_attribute_name("fill")
            "fillClr"
            >>> handler._map_attribute_name("visibility")
            "visibility"
        """
        # Use color attribute map for color properties
        if attribute in COLOR_ATTRIBUTES:
            return COLOR_ATTRIBUTE_NAME_MAP.get(attribute, attribute)
        # Use standard attribute map for everything else
        return ATTRIBUTE_NAME_MAP.get(attribute, attribute)

    def _build_color_value_block(self, color_value: str) -> str:
        """Build <a:to> block for color values.

        Args:
            color_value: Color value to set (e.g., "#ff0000", "red")

        Returns:
            XML string for <a:to> with <a:srgbClr>

        Example:
            >>> handler._build_color_value_block("#ff0000")
            '<a:to>\\n    <a:srgbClr val="ff0000"/>\\n</a:to>\\n'
        """
        hex_color = self._processor.parse_color(color_value)
        return (
            f'                                        <a:to>\n'
            f'                                            <a:srgbClr val="{hex_color}"/>\n'
            f'                                        </a:to>\n'
        )

    def _build_numeric_value_block(self, ppt_attribute: str, value: str) -> str:
        """Build <a:to> block for numeric values.

        Args:
            ppt_attribute: PowerPoint attribute name (for normalization)
            value: Numeric value to set

        Returns:
            XML string for <a:to> with <a:val>

        Example:
            >>> handler._build_numeric_value_block("ppt_x", "100")
            '<a:to>\\n    <a:val val="914400"/>\\n</a:to>\\n'
        """
        normalized_value = self._normalize_value(ppt_attribute, value)
        escaped_value = self._escape_value(normalized_value)
        return (
            f'                                        <a:to>\n'
            f'                                            <a:val val="{escaped_value}"/>\n'
            f'                                        </a:to>\n'
        )

    def _normalize_value(self, ppt_attribute: str, value: str) -> str:
        """Normalize numeric value based on attribute type.

        Uses ValueProcessor to convert values to PowerPoint units:
        - Angle attributes → 60000ths of a degree
        - Position/size attributes → EMU

        Args:
            ppt_attribute: PowerPoint attribute name
            value: Raw value string

        Returns:
            Normalized value as string

        Example:
            >>> handler._normalize_value("ppt_angle", "45")
            "2700000"  # 45 * 60000
        """
        return self._processor.normalize_numeric_value(
            ppt_attribute, value, unit_converter=self._units
        )

    def _escape_value(self, value: str) -> str:
        """Escape value for XML attribute.

        Args:
            value: Value to escape

        Returns:
            Escaped value

        Example:
            >>> handler._escape_value('100"200')
            '100&quot;200'
        """
        # Simple escaping for quotes
        return value.replace('"', '&quot;')
