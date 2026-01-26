"""Numeric animation handler.

This module handles numeric animations (x, y, width, height, etc.).
Generates PowerPoint <a:anim> with from/to numeric values and optional keyframes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from textwrap import indent

from lxml import etree

from .base import AnimationHandler, AnimationDefinition
from ..constants import FADE_ATTRIBUTES, COLOR_ATTRIBUTES, ATTRIBUTE_NAME_MAP
from ..value_formatters import format_numeric_value
from svg2ooxml.drawingml.xml_builder import to_string

if TYPE_CHECKING:
    from svg2ooxml.common.units import UnitConverter
    from ..tav_builder import TAVBuilder
    from ..value_processors import ValueProcessor
    from ..xml_builders import AnimationXMLBuilder

__all__ = ["NumericAnimationHandler"]


class NumericAnimationHandler(AnimationHandler):
    """Handler for numeric animations.

    Handles animations on numeric attributes: x, y, width, height, stroke-width, etc.
    Generates PowerPoint <a:anim> with from/to values and optional TAV keyframes.

    PowerPoint numeric animations use:
    - <a:from><a:val val="..."/></a:from> for starting value
    - <a:to><a:val val="..."/></a:to> for ending value
    - Optional <a:tavLst> for multi-keyframe animations

    Values are normalized based on attribute type:
    - Angles → PowerPoint angle units (60000ths of a degree)
    - Positions/sizes → EMU (English Metric Units)

    Example:
        >>> handler = NumericAnimationHandler(xml_builder, value_processor, tav_builder, unit_converter)
        >>> animation = Mock(attribute_name="x", values=["0", "100"], duration_ms=1000)
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
        """Initialize numeric animation handler.

        Args:
            xml_builder: XML builder for creating PowerPoint elements
            value_processor: Processor for normalizing animation values
            tav_builder: Builder for creating keyframe (TAV) lists
            unit_converter: Converter for SVG units to PowerPoint EMU
        """
        super().__init__(xml_builder, value_processor, tav_builder, unit_converter)

    def can_handle(self, animation: AnimationDefinition) -> bool:
        """Check if this handler can process the animation.

        Handles numeric animations that are not handled by specialized handlers.
        Only processes ANIMATE type (not ANIMATE_MOTION, ANIMATE_TRANSFORM, etc.)
        Specifically excludes:
        - Fade attributes (handled by OpacityHandler)
        - Color attributes (handled by ColorHandler)
        - Non-ANIMATE animation types

        Args:
            animation: Animation definition to check

        Returns:
            True if attribute_name is a numeric attribute and type is ANIMATE

        Example:
            >>> handler.can_handle(animation)
            True  # if animation.target_attribute == "x" and type is ANIMATE
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

        # Exclude attributes handled by other handlers
        target_attribute = self._resolve_target_attribute(animation)
        if target_attribute is None:
            return False

        if target_attribute in FADE_ATTRIBUTES:
            return False
        if target_attribute in COLOR_ATTRIBUTES:
            return False

        # Handle remaining numeric attributes
        return True

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        """Build PowerPoint timing XML for numeric animation.

        Generates <p:par> container with <a:anim> element containing:
        - <a:cBhvr> with attribute name list
        - <a:from> with starting value
        - <a:to> with ending value
        - Optional <a:tavLst> for multi-keyframe animations

        Args:
            animation: Animation definition to convert
            par_id: Unique ID for the <p:par> element
            behavior_id: Unique ID for the behavior element

        Returns:
            PowerPoint timing XML as string

        Example:
            >>> xml = handler.build(animation, par_id=1, behavior_id=2)
            >>> # Returns: '<p:par>...<a:anim>...<a:from>...<a:to>...</a:anim>...</p:par>'
        """
        # Validate we have values
        if not animation.values:
            return ""

        # Map attribute name to PowerPoint attribute
        target_attribute = self._resolve_target_attribute(animation) or ""
        ppt_attribute = self._map_attribute_name(target_attribute)

        # Normalize from/to values
        from_value = self._normalize_value(ppt_attribute, animation.values[0])
        to_value = self._normalize_value(ppt_attribute, animation.values[-1])

        # Build TAV list if multi-keyframe
        tav_elements, needs_custom_ns = self._build_numeric_tav_list(
            animation, ppt_attribute
        )

        # Build attribute name list
        attr_list = self._xml.build_attribute_list([ppt_attribute])

        # Build behavior core with attribute list
        behavior_core = self._xml.build_behavior_core(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id if hasattr(animation, "element_id") else "",
            attribute_list=attr_list,
        )

        # Build TAV list container
        # For simple from/to animations, we create two TAV entries
        if not tav_elements:
            from_tav = self._xml.build_tav_element(
                tm=0,
                value_elem=self._xml.build_numeric_value(from_value)
            )
            to_tav = self._xml.build_tav_element(
                tm=100000,
                value_elem=self._xml.build_numeric_value(to_value)
            )
            tav_container = self._xml.build_tav_list_container([from_tav, to_tav])
        else:
            tav_container = self._xml.build_tav_list_container(tav_elements)
            
        tav_string = to_string(tav_container)
        tav_block = "\n" + indent(tav_string, " " * 40) + "\n"

        # Build anim element
        anim_tag = "<p:anim"
        if needs_custom_ns:
            from ..constants import SVG2_ANIMATION_NS
            anim_tag += f' xmlns:svg2="{SVG2_ANIMATION_NS}"'
        anim_tag += ">"

        anim_elem = (
            f'                                    {anim_tag}\n'
            f'{behavior_core}'
            f'{tav_block}'
            f'                                    </p:anim>'
        )

        # Build par container
        par = self._xml.build_par_container(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_content=anim_elem,
            preset_id=0,
            preset_class="entr",
            preset_subtype=0,
            node_type="withEffect",
        )

        return par

    def _map_attribute_name(self, attribute: str) -> str:
        """Map SVG attribute name to PowerPoint attribute name.

        Args:
            attribute: SVG attribute name (e.g., "x", "width", "rotate")

        Returns:
            PowerPoint attribute name (e.g., "ppt_x", "ppt_w", "ppt_angle")

        Example:
            >>> handler._map_attribute_name("x")
            "ppt_x"
            >>> handler._map_attribute_name("width")
            "ppt_w"
        """
        return ATTRIBUTE_NAME_MAP.get(attribute, attribute)

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

    def _build_numeric_tav_list(
        self,
        animation: AnimationDefinition,
        ppt_attribute: str,
    ) -> tuple[list, bool]:
        """Build TAV list for multi-keyframe numeric animations.

        Only builds TAV list if:
        - More than 2 values, OR
        - Explicit key_times provided

        Each value is normalized based on attribute type.

        Args:
            animation: Animation definition
            ppt_attribute: PowerPoint attribute name for normalization

        Returns:
            Tuple of (tav_elements, needs_custom_namespace)

        Example:
            >>> elements, needs_ns = handler._build_numeric_tav_list(animation, "ppt_x")
            >>> # Returns: ([<tav1>, <tav2>, ...], True) if keyframes exist
        """
        values = animation.values
        if not values or (len(values) <= 2 and not animation.key_times):
            return ([], False)

        # Normalize all values first
        normalized_values = [
            self._normalize_value(ppt_attribute, val) for val in values
        ]

        # Create a value formatter that wraps the normalized values
        def numeric_value_formatter(value: str) -> etree._Element:
            """Format already-normalized numeric value."""
            return format_numeric_value(value)

        # Build TAV list using tav_builder with normalized values
        tav_elements, needs_ns = self._tav.build_tav_list(
            values=normalized_values,
            key_times=animation.key_times,
            key_splines=animation.key_splines,
            duration_ms=animation.duration_ms,
            value_formatter=numeric_value_formatter,
        )

        return (tav_elements, needs_ns)

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
