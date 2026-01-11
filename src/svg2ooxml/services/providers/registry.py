"""Lightweight registry used to wire conversion service providers.

The registry keeps a mapping of provider names (``filter``, ``gradient``,
``pattern``, ``image``, …) to callables that build the concrete service
objects.  Providers are registered at import time by the modules under
``svg2ooxml.services.providers`` so ``configure_services`` can materialise
fresh service instances for each parse.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from importlib import import_module
from typing import Any

ProviderFactory = Callable[[], Any]

_PROVIDERS: dict[str, ProviderFactory] = {}
_DEFAULT_PROVIDER_MODULES: tuple[str, ...] = (
    "color_provider",
    "font_provider",
    "gradient_provider",
    "filter_provider",
    "marker_provider",
    "pattern_provider",
    "symbol_provider",
    "drawingml_provider",
    "image_provider",
    "mask_provider",
    "hyperlink_provider",
)
_LOADED: set[str] = set()


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register a factory for the given service name."""
    if not name:
        raise ValueError("provider name must be non-empty")
    if not callable(factory):
        raise TypeError("provider factory must be callable")
    _PROVIDERS[name] = factory


def get_provider(name: str) -> ProviderFactory | None:
    """Return the provider factory for *name* if registered."""
    return _PROVIDERS.get(name)


def iter_providers() -> Iterable[tuple[str, ProviderFactory]]:
    """Yield the provider registry contents."""
    return tuple(_PROVIDERS.items())


def clear_providers() -> None:
    """Reset the registry (intended for tests)."""
    _PROVIDERS.clear()
    _LOADED.clear()


def ensure_default_providers(modules: Iterable[str] | None = None) -> None:
    """Import default provider modules so they register themselves."""
    entries = modules or _DEFAULT_PROVIDER_MODULES
    for name in entries:
        if name in _LOADED:
            continue
        import_module(f"svg2ooxml.services.providers.{name}")
        _LOADED.add(name)


def get_provider_factories() -> dict[str, ProviderFactory]:
    """Return the provider registry after ensuring defaults are loaded."""
    ensure_default_providers()
    return dict(_PROVIDERS)


__all__ = [
    "ProviderFactory",
    "register_provider",
    "get_provider",
    "iter_providers",
    "clear_providers",
    "ensure_default_providers",
    "get_provider_factories",
]
