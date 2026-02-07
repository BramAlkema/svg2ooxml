"""Service bootstrap helpers for parser-facing workflows.

This mirrors svg2pptx's conversion service setup so batch/preprocess entries can
obtain the same ConversionServices container the parser expects.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.common.style.resolver import StyleResolver
    from svg2ooxml.core.parser.units import UnitConverter
    from svg2ooxml.services import ConversionServices
from svg2ooxml.core.conversion_context import build_conversion_context
from svg2ooxml.policy import PolicyContext, PolicyEngine


@dataclass(frozen=True)
class ParserServices:
    """Container exposing the service registry used by the parser."""

    services: ConversionServices
    policy_engine: PolicyEngine
    policy_context: PolicyContext
    unit_converter: UnitConverter | None = None
    style_resolver: StyleResolver | None = None


def build_parser_services(
    *,
    overrides: Mapping[str, Any] | None = None,
    policy_engine: PolicyEngine | None = None,
    policy_context: PolicyContext | None = None,
    policy_name: str | None = None,
    include_defaults: bool = True,
    **service_overrides: Any,
) -> ParserServices:
    """Return parser services configured with defaults and optional overrides."""

    service_map: dict[str, Any] = {}
    if overrides:
        service_map.update(overrides)
    if service_overrides:
        service_map.update(service_overrides)

    context = build_conversion_context(
        overrides=service_map or None,
        policy_engine=policy_engine,
        policy_context=policy_context,
        policy_name=policy_name,
        include_defaults=include_defaults,
    )
    return ParserServices(
        services=context.services,
        policy_engine=context.policy_engine,
        policy_context=context.policy_context,
        unit_converter=context.unit_converter,
        style_resolver=context.style_resolver,
    )


__all__ = ["ParserServices", "build_parser_services"]
