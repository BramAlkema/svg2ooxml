"""Helpers for wiring default service providers."""

from __future__ import annotations

from importlib import import_module
from typing import Iterable

DEFAULT_PROVIDER_MODULES: tuple[str, ...] = (
    "svg2ooxml.services.providers.filter_provider",
    "svg2ooxml.services.providers.gradient_provider",
    "svg2ooxml.services.providers.pattern_provider",
    "svg2ooxml.services.providers.image_provider",
    "svg2ooxml.services.providers.mask_provider",
    "svg2ooxml.services.providers.drawingml_provider",
    "svg2ooxml.services.providers.marker_provider",
    "svg2ooxml.services.providers.symbol_provider",
    "svg2ooxml.services.providers.font_provider",
    "svg2ooxml.services.providers.hyperlink_provider",
    "svg2ooxml.services.providers.color_provider",
)

_extra_modules: list[str] = []
_loaded: bool = False


def ensure_default_providers() -> None:
    """Import provider modules once so they register themselves."""
    global _loaded
    if _loaded:
        return
    modules: Iterable[str] = DEFAULT_PROVIDER_MODULES + tuple(_extra_modules)
    for module in modules:
        import_module(module)
    _loaded = True


def register_additional_providers(module: str) -> None:
    """Allow tests or extensions to register extra provider modules."""
    if not module:
        raise ValueError("module must be non-empty")
    if module in _extra_modules:
        return
    _extra_modules.append(module)
    # If we've already loaded defaults, import immediately.
    if _loaded:
        import_module(module)


__all__ = ["ensure_default_providers", "register_additional_providers"]
