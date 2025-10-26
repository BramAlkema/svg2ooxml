"""Lightweight registry used to wire conversion service providers.

The registry keeps a mapping of provider names (``filter``, ``gradient``,
``pattern``, ``image``, …) to callables that build the concrete service
objects.  Providers are registered at import time by the modules under
``svg2ooxml.services.providers`` so ``configure_services`` can materialise
fresh service instances for each parse.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Iterable

ProviderFactory = Callable[[], Any]

_PROVIDERS: dict[str, ProviderFactory] = {}


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


__all__ = [
    "ProviderFactory",
    "register_provider",
    "get_provider",
    "iter_providers",
    "clear_providers",
]
