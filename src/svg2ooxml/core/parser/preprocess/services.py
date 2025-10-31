"""Service bootstrap helpers for parser-facing workflows.

This mirrors svg2pptx's conversion service setup so batch/preprocess entries can
obtain the same ConversionServices container the parser expects.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.services import ConversionServices
from svg2ooxml.policy import PolicyContext, PolicyEngine, build_policy_engine


@dataclass(frozen=True)
class ParserServices:
    """Container exposing the service registry used by the parser."""

    services: "ConversionServices"
    policy_engine: PolicyEngine
    policy_context: PolicyContext


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

    from svg2ooxml.services import configure_services  # local import to avoid circular dependency

    services = configure_services(service_map, include_defaults=include_defaults)

    engine = policy_engine or build_policy_engine(policy_name)
    if policy_engine is not None and policy_name:
        engine.set_policy(policy_name)

    context = policy_context or engine.evaluate()
    return ParserServices(services=services, policy_engine=engine, policy_context=context)


__all__ = ["ParserServices", "build_parser_services"]
