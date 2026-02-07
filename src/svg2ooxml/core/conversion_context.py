"""Shared conversion context helpers for parser and IR wiring."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from svg2ooxml.common.style.resolver import StyleResolver
from svg2ooxml.core.parser.units import UnitConverter
from svg2ooxml.policy import PolicyContext, PolicyEngine, build_policy_engine
from svg2ooxml.services import ConversionServices, configure_services


@dataclass(frozen=True)
class ConversionContextBundle:
    """Normalized services + policy + style state used during conversion."""

    services: ConversionServices
    policy_engine: PolicyEngine
    policy_context: PolicyContext
    unit_converter: UnitConverter
    style_resolver: StyleResolver

    def clone(
        self,
        *,
        policy_context: PolicyContext | None = None,
        unit_converter: UnitConverter | None = None,
        style_resolver: StyleResolver | None = None,
    ) -> ConversionContextBundle:
        services = _clone_services(self.services)
        engine = self.policy_engine
        context = policy_context or clone_policy_context(self.policy_context)
        if context is None:
            context = engine.evaluate()
        unit_converter = unit_converter or self.unit_converter
        style_resolver = style_resolver or self.style_resolver
        _register_context_services(services, engine, context, unit_converter, style_resolver)
        return ConversionContextBundle(
            services=services,
            policy_engine=engine,
            policy_context=context,
            unit_converter=unit_converter,
            style_resolver=style_resolver,
        )


def build_conversion_context(
    *,
    services: ConversionServices | None = None,
    overrides: Mapping[str, Any] | None = None,
    policy_engine: PolicyEngine | None = None,
    policy_context: PolicyContext | None = None,
    policy_name: str | None = None,
    include_defaults: bool = True,
    unit_converter: UnitConverter | None = None,
    style_resolver: StyleResolver | None = None,
    clone_services: bool = True,
    **service_overrides: Any,
) -> ConversionContextBundle:
    """Build a conversion context with unified policy/service wiring."""

    service_map: dict[str, Any] = {}
    if overrides:
        service_map.update(overrides)
    if service_overrides:
        service_map.update(service_overrides)

    policy_engine = policy_engine or service_map.pop("policy_engine", None)
    policy_context = policy_context or service_map.pop("policy_context", None)
    unit_converter = unit_converter or service_map.pop("unit_converter", None)
    style_resolver = style_resolver or service_map.pop("style_resolver", None)

    engine = resolve_policy_engine(
        policy_engine=policy_engine,
        fallback_engine=None,
        policy_name=policy_name,
    )

    context = policy_context or engine.evaluate()

    base_services = services
    if base_services is None:
        services = configure_services(
            service_map,
            include_defaults=include_defaults,
            policy_engine=engine,
            policy_context=context,
        )
    else:
        services = _clone_services(base_services) if clone_services else base_services
        for name, value in service_map.items():
            services.register(name, value)
        services.register("policy_engine", engine)
        services.register("policy_context", context)

    unit_converter, style_resolver = _resolve_unit_and_style(
        services=services,
        unit_converter=unit_converter,
        style_resolver=style_resolver,
    )
    _register_context_services(services, engine, context, unit_converter, style_resolver)

    return ConversionContextBundle(
        services=services,
        policy_engine=engine,
        policy_context=context,
        unit_converter=unit_converter,
        style_resolver=style_resolver,
    )


def resolve_policy_engine(
    *,
    policy_engine: PolicyEngine | None,
    fallback_engine: PolicyEngine | None = None,
    policy_name: str | None = None,
) -> PolicyEngine:
    """Resolve a policy engine, optionally avoiding mutation of fallback engines."""

    engine = policy_engine or fallback_engine
    if engine is None:
        return build_policy_engine(policy_name)
    if policy_name:
        if policy_engine is None and fallback_engine is engine:
            return build_policy_engine(policy_name)
        engine.set_policy(policy_name)
    return engine


def resolve_policy_context(
    *,
    policy_context: PolicyContext | None,
    policy_engine: PolicyEngine,
    fallback_context: PolicyContext | None = None,
    fallback_engine: PolicyEngine | None = None,
    allow_fallback: bool = True,
) -> PolicyContext:
    """Resolve a policy context for the provided engine."""

    if policy_context is not None:
        return policy_context
    if allow_fallback and fallback_context is not None and fallback_engine is policy_engine:
        cloned = clone_policy_context(fallback_context)
        if cloned is not None:
            return cloned
    return policy_engine.evaluate()


def clone_policy_context(context: PolicyContext | None) -> PolicyContext | None:
    """Copy a policy context to avoid sharing selections between runs."""

    if context is None:
        return None
    return PolicyContext(selections=dict(context.selections))


def _clone_services(services: ConversionServices) -> ConversionServices:
    clone = getattr(services, "clone", None)
    if callable(clone):
        return clone()
    return services


def _resolve_unit_and_style(
    *,
    services: ConversionServices | None,
    unit_converter: UnitConverter | None,
    style_resolver: StyleResolver | None,
) -> tuple[UnitConverter, StyleResolver]:
    if unit_converter is None and style_resolver is not None:
        unit_converter = getattr(style_resolver, "_unit_converter", None)

    if unit_converter is None and services is not None:
        unit_converter = services.resolve("unit_converter")

    if style_resolver is None and services is not None:
        style_resolver = services.resolve("style_resolver")

    if unit_converter is None and style_resolver is not None:
        unit_converter = getattr(style_resolver, "_unit_converter", None)

    unit_converter = unit_converter or UnitConverter()
    style_resolver = style_resolver or StyleResolver(unit_converter)
    return unit_converter, style_resolver


def _register_context_services(
    services: ConversionServices,
    engine: PolicyEngine,
    context: PolicyContext,
    unit_converter: UnitConverter,
    style_resolver: StyleResolver,
) -> None:
    services.register("policy_engine", engine)
    services.register("policy_context", context)
    if services.resolve("unit_converter") is not unit_converter:
        services.register("unit_converter", unit_converter)
    if services.resolve("style_resolver") is not style_resolver:
        services.register("style_resolver", style_resolver)


__all__ = [
    "ConversionContextBundle",
    "build_conversion_context",
    "clone_policy_context",
    "resolve_policy_context",
    "resolve_policy_engine",
]
