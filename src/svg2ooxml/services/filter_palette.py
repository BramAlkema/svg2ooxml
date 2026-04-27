"""Palette resolver discovery for filter fallbacks."""

from __future__ import annotations

from typing import Any, cast

from svg2ooxml.drawingml.emf_primitives import PaletteResolver


def extract_palette_resolver(services: Any) -> PaletteResolver | None:
    candidate_names = (
        "filter_palette_resolver",
        "palette_resolver",
        "filter_palette",
    )
    for name in candidate_names:
        resolver = services.resolve(name)
        if resolver is None:
            resolver = getattr(services, name, None)
        coerced = coerce_palette_resolver(resolver)
        if coerced is not None:
            return coerced

    theming_candidates = (
        services.resolve("theme"),
        services.resolve("theming"),
        getattr(services, "theme_service", None),
        getattr(services, "theming_service", None),
    )
    for theming in theming_candidates:
        coerced = coerce_palette_resolver(theming)
        if coerced is not None:
            return coerced
        if theming is None:
            continue
        attr_names = (
            "resolve_filter_palette",
            "get_filter_palette_resolver",
            "palette_resolver",
            "resolve_palette",
            "resolve",
        )
        for attr in attr_names:
            bound = getattr(theming, attr, None)
            coerced = coerce_palette_resolver(bound)
            if coerced is not None:
                return coerced

    return None


def coerce_palette_resolver(candidate: Any) -> PaletteResolver | None:
    if candidate is None:
        return None
    if callable(candidate):
        return cast(PaletteResolver, candidate)
    method_names = (
        "resolve_filter_palette",
        "get_filter_palette_resolver",
        "palette_resolver",
        "resolve_palette",
        "resolve",
    )
    for name in method_names:
        method = getattr(candidate, name, None)
        if callable(method):
            return cast(PaletteResolver, method)
    return None


__all__ = ["coerce_palette_resolver", "extract_palette_resolver"]
