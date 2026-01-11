"""Service wiring helper."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .conversion import ConversionServices
from .font_converter import build_smart_font_converter
from .clip_service import StructuredClipService
from .providers import registry as provider_registry
from svg2ooxml.elements import (
    create_gradient_processor,
    create_image_processor,
    create_pattern_processor,
)


def configure_services(
    overrides: Mapping[str, Any] | None = None,
    *,
    include_defaults: bool = True,
    filter_strategy: str | None = None,
    policy_engine: Any | None = None,
    policy_context: Any | None = None,
    policy_name: str | None = None,
    **legacy_overrides: Any,
) -> ConversionServices:
    """Materialise a ``ConversionServices`` container.

    ``overrides`` (or ``legacy`` keyword arguments) can be used to inject pre-built
    service instances.  When ``include_defaults`` is ``True`` (the default) the
    registered providers for filters, gradients, patterns, and images are used.
    """
    services = ConversionServices()
    override_map: dict[str, Any] = {}
    if overrides:
        override_map.update(overrides)
    if legacy_overrides:
        override_map.update(legacy_overrides)

    if "policy_engine" in override_map and policy_engine is None:
        policy_engine = override_map.pop("policy_engine")
    if "policy_context" in override_map and policy_context is None:
        policy_context = override_map.pop("policy_context")

    if policy_engine is None and policy_name:
        from svg2ooxml.policy import build_policy_engine

        policy_engine = build_policy_engine(policy_name)
    elif policy_engine is not None and policy_name:
        setter = getattr(policy_engine, "set_policy", None)
        if callable(setter):
            setter(policy_name)

    if policy_engine is not None:
        services.register("policy_engine", policy_engine)
    if policy_context is not None:
        services.register("policy_context", policy_context)

    if include_defaults:
        provider_registry.ensure_default_providers()
        for name, factory in provider_registry.iter_providers():
            if name in override_map:
                services.register(name, override_map.pop(name))
            else:
                services.register(name, factory())

    for name, provider in override_map.items():
        services.register(name, provider)

    # Attach lightweight processors so callers can rely on familiar APIs.
    if services.gradient_service:
        gradient_processor = services.resolve("gradient_processor")
        if gradient_processor is None:
            gradient_processor = create_gradient_processor(services)
            services.register("gradient_processor", gradient_processor)
        setter = getattr(services.gradient_service, "set_processor", None)
        if callable(setter):
            setter(gradient_processor)

    if services.pattern_service:
        pattern_processor = services.resolve("pattern_processor")
        if pattern_processor is None:
            pattern_processor = create_pattern_processor(services)
            services.register("pattern_processor", pattern_processor)
        setter = getattr(services.pattern_service, "set_processor", None)
        if callable(setter):
            setter(pattern_processor)

    if services.image_service and not services.resolve("image_processor"):
        services.register("image_processor", create_image_processor(services))

    if services.smart_font_converter is None:
        services.register(
            "smart_font_converter",
            build_smart_font_converter(
                services,
                logger=logging.getLogger("svg2ooxml.smart_font"),
            ),
        )

    if services.resolve("clip_service") is None:
        services.register("clip_service", StructuredClipService(services))

    if services.resolve("mask_service") is None:
        from svg2ooxml.services.mask_service import StructuredMaskService

        services.register("mask_service", StructuredMaskService(services))

    if services.resolve("emf_path_adapter") is None:
        from svg2ooxml.drawingml.bridges import EMFPathAdapter

        services.register("emf_path_adapter", EMFPathAdapter())

    if services.resolve("mask_processor") is None:
        from svg2ooxml.core.masks import MaskProcessor

        services.register("mask_processor", MaskProcessor(services))

    if services.resolve("mask_asset_store") is None:
        from svg2ooxml.drawingml.mask_store import MaskAssetStore

        services.register("mask_asset_store", MaskAssetStore())

    if filter_strategy is not None and services.filter_service is not None:
        try:
            services.filter_service.set_strategy(filter_strategy)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid filter strategy '{filter_strategy}': {exc}") from exc
    return services


__all__ = ["configure_services"]
