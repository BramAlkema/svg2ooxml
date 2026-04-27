"""Planning primitives for native PowerPoint animation emission."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from lxml import etree

from svg2ooxml.drawingml.xml_builder import NS_P

__all__ = ["NativeFragment"]


@dataclass(frozen=True, slots=True)
class NativeFragment:
    """One native emission unit ready for timing-tree assembly.

    Today this wraps an already-built ``<p:par>`` element. The important part is
    the contract: handlers and planners can return a typed fragment with
    explicit provenance instead of making the writer infer intent from raw XML.
    """

    par: etree._Element
    source: str = "legacy-handler"
    strategy: str = "prebuilt-par"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.par.tag != f"{{{NS_P}}}par":
            raise ValueError("NativeFragment.par must be a <p:par> element")

    @classmethod
    def from_legacy_par(
        cls,
        par: etree._Element,
        *,
        source: str = "legacy-handler",
        strategy: str = "prebuilt-par",
        metadata: Mapping[str, Any] | None = None,
    ) -> NativeFragment:
        """Wrap an existing handler-produced ``<p:par>`` without changing behavior."""
        return cls(
            par=par,
            source=source,
            strategy=strategy,
            metadata=dict(metadata or {}),
        )
