"""Result objects for parser operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .style_context import StyleContext as ParserStyleContext
    from svg2ooxml.policy import PolicyContext, PolicyEngine
    from svg2ooxml.services.conversion import ConversionServices
    from svg2ooxml.ir.fonts import FontFaceRule, SvgFontDefinition


@dataclass(slots=True)
class ParseResult:
    """Lightweight capture of parser outcomes."""

    success: bool
    svg_root: Any | None
    error: str | None = None
    processing_time_ms: float = 0.0
    element_count: int = 0
    namespace_count: int = 0
    namespaces: dict[str | None, str] | None = None
    has_external_references: bool = False
    masks: dict[str, Any] | None = None
    symbols: dict[str, Any] | None = None
    filters: dict[str, Any] | None = None
    markers: dict[str, Any] | None = None
    root_style: dict[str, Any] | None = None
    normalization_changes: dict[str, Any] | None = None
    normalization_applied: bool = False
    width_px: float | None = None
    height_px: float | None = None
    animations: list[Any] | None = None
    viewbox_scale: tuple[float, float] | None = None
    root_color: tuple[float, float, float, float] | None = None
    services: "ConversionServices | None" = None
    policy_engine: "PolicyEngine | None" = None
    policy_context: "PolicyContext | None" = None
    style_context: "ParserStyleContext | None" = None
    web_fonts: "list[FontFaceRule] | None" = None
    svg_fonts: "list[SvgFontDefinition] | None" = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success_with(
        cls,
        svg_root: Any,
        element_count: int,
        *,
        namespace_count: int = 0,
        namespaces: dict[str | None, str] | None = None,
        has_external_references: bool = False,
        masks: dict[str, Any] | None = None,
        symbols: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
        markers: dict[str, Any] | None = None,
        root_style: dict[str, Any] | None = None,
        width_px: float | None = None,
        height_px: float | None = None,
        animations: list[Any] | None = None,
        viewbox_scale: tuple[float, float] | None = None,
        root_color: tuple[float, float, float, float] | None = None,
        normalization_changes: dict[str, Any] | None = None,
        normalization_applied: bool = False,
        processing_time_ms: float = 0.0,
        services: "ConversionServices | None" = None,
        policy_engine: "PolicyEngine | None" = None,
        policy_context: "PolicyContext | None" = None,
        style_context: "ParserStyleContext | None" = None,
        web_fonts: "list[FontFaceRule] | None" = None,
        svg_fonts: "list[SvgFontDefinition] | None" = None,
    ) -> ParseResult:
        """Construct a success result."""
        return cls(
            success=True,
            svg_root=svg_root,
            element_count=element_count,
            namespace_count=namespace_count,
            namespaces=namespaces,
            has_external_references=has_external_references,
            masks=masks,
            symbols=symbols,
            filters=filters,
            markers=markers,
            root_style=root_style,
            width_px=width_px,
            height_px=height_px,
            animations=animations,
            viewbox_scale=viewbox_scale,
            root_color=root_color,
            normalization_changes=normalization_changes,
            normalization_applied=normalization_applied,
            processing_time_ms=processing_time_ms,
            services=services,
            policy_engine=policy_engine,
            policy_context=policy_context,
            style_context=style_context,
            web_fonts=web_fonts,
            svg_fonts=svg_fonts,
        )

    @classmethod
    def failure(
        cls,
        message: str,
        *,
        processing_time_ms: float = 0.0,
        services: "ConversionServices | None" = None,
        policy_engine: "PolicyEngine | None" = None,
        policy_context: "PolicyContext | None" = None,
        style_context: "ParserStyleContext | None" = None,
    ) -> ParseResult:
        """Construct a failure result."""
        return cls(
            success=False,
            svg_root=None,
            error=message,
            processing_time_ms=processing_time_ms,
            services=services,
            policy_engine=policy_engine,
            policy_context=policy_context,
            style_context=style_context,
        )


__all__ = ["ParseResult"]
