"""Entry points for converting parser results into IR scenes."""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from svg2ooxml.core.conversion_context import (
    build_conversion_context,
    resolve_policy_context,
    resolve_policy_engine,
)
from svg2ooxml.core.ir.converter import IRConverter, IRScene
from svg2ooxml.core.parser import ParseResult
from svg2ooxml.policy import PolicyContext, PolicyEngine
from svg2ooxml.services import ConversionServices

if TYPE_CHECKING:  # pragma: no cover - hint only
    from svg2ooxml.core.tracing import ConversionTracer


def convert_parser_output(
    parser_result: ParseResult,
    services: ConversionServices | None = None,
    policy_engine: PolicyEngine | None = None,
    policy_context: PolicyContext | None = None,
    *,
    policy_name: str | None = None,
    logger: logging.Logger | None = None,
    tracer: "ConversionTracer | None" = None,
) -> IRScene:
    """Convert a parser result into an IR scene graph."""

    base_services = services or parser_result.services
    engine = resolve_policy_engine(
        policy_engine=policy_engine,
        fallback_engine=parser_result.policy_engine,
        policy_name=policy_name,
    )
    resolved_context = resolve_policy_context(
        policy_context=policy_context,
        policy_engine=engine,
        fallback_context=parser_result.policy_context,
        fallback_engine=parser_result.policy_engine,
        allow_fallback=policy_engine is None and policy_name is None,
    )
    conversion_context = build_conversion_context(
        services=base_services,
        policy_engine=engine,
        policy_context=resolved_context,
        clone_services=services is None,
    )
    services = conversion_context.services
    engine = conversion_context.policy_engine
    policy_context = conversion_context.policy_context

    _hydrate_services_from_parser(services, parser_result, logger)

    pre_stage_events: list[tuple[str, str, str | None, dict[str, Any]]] = []
    if tracer is not None:
        snapshot = tracer.report()
        pre_stage_events = [
            (event.stage, event.action, event.subject, dict(event.metadata or {}))
            for event in snapshot.stage_events
        ]

    converter = IRConverter(
        services=services,
        logger=logger,
        policy_engine=engine,
        policy_context=policy_context,
        tracer=tracer,
    )
    if pre_stage_events:
        converter.preload_stage_events(pre_stage_events)
    return converter.convert(parser_result)


def _hydrate_services_from_parser(
    services: ConversionServices,
    parser_result: ParseResult,
    logger: logging.Logger | None = None,
) -> None:
    """Ensure DI services pick up parser-collected definitions."""

    resource_map = {
        "filters": parser_result.filters,
        "markers": parser_result.markers,
        "symbols": parser_result.symbols,
    }

    for name, definitions in resource_map.items():
        if not definitions:
            continue
        try:
            services.register(name, dict(definitions))
        except Exception as exc:  # pragma: no cover - defensive logging
            if logger:
                logger.warning("Failed to register %s definitions: %s", name, exc)

    # Register web fonts with FontService
    if parser_result.web_fonts:
        font_service = services.resolve("font")
        if font_service is not None:
            try:
                from svg2ooxml.services.fonts.providers.webfont import WebFontProvider
                from svg2ooxml.services.fonts.loader import FontLoader
                from svg2ooxml.services.fonts.fetcher import FontFetcher

                # Create font loader with fetcher for remote fonts
                fetcher = FontFetcher()
                loader = FontLoader(fetcher=fetcher, allow_network=True)

                # Create provider with loader enabled
                provider = WebFontProvider(
                    rules=tuple(parser_result.web_fonts),
                    loader=loader,
                    enable_loading=True,
                    cache_loaded_fonts=True
                )
                # Prepend to give web fonts priority over system fonts
                font_service.prepend_provider(provider)
                if logger:
                    logger.debug(
                        "Registered WebFontProvider with %d font face(s) and font loading enabled",
                        len(parser_result.web_fonts)
                    )
            except Exception as exc:  # pragma: no cover - defensive logging
                if logger:
                    logger.warning("Failed to register web fonts: %s", exc)


__all__ = ["IRScene", "convert_parser_output"]
