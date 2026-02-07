"""Base handler for animation types.

This module defines the abstract base class for all animation handlers.
Each handler specializes in converting specific animation types from SVG
to PowerPoint timing XML.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from lxml import etree

if TYPE_CHECKING:
    from svg2ooxml.common.units import UnitConverter
    from svg2ooxml.ir.animation import AnimationDefinition

    from ..tav_builder import TAVBuilder
    from ..value_processors import ValueProcessor
    from ..xml_builders import AnimationXMLBuilder

__all__ = ["AnimationHandler"]


class AnimationHandler(ABC):
    """Abstract base class for animation handlers.

    Each handler specializes in building PowerPoint XML for specific
    animation types (opacity, color, transform, numeric, motion, set).

    Handlers receive dependencies via constructor injection and return
    lxml elements from ``build()`` — the writer serializes once at the end.
    """

    def __init__(
        self,
        xml_builder: AnimationXMLBuilder,
        value_processor: ValueProcessor,
        tav_builder: TAVBuilder,
        unit_converter: UnitConverter,
    ):
        self._xml = xml_builder
        self._processor = value_processor
        self._tav = tav_builder
        self._units = unit_converter

    @abstractmethod
    def can_handle(self, animation: AnimationDefinition) -> bool:
        """Return ``True`` if this handler can process *animation*."""
        ...

    @abstractmethod
    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element | None:
        """Build a ``<p:par>`` element for *animation*, or ``None`` to skip."""
        ...
