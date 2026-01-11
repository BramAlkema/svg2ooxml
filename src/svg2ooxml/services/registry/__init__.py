"""Service registry helpers (compat shim)."""

from __future__ import annotations

from svg2ooxml.services.providers.registry import (
    ProviderFactory,
    clear_providers,
    ensure_default_providers,
    get_provider,
    get_provider_factories,
    iter_providers,
    register_provider,
)

__all__ = [
    "ProviderFactory",
    "register_provider",
    "ensure_default_providers",
    "get_provider",
    "iter_providers",
    "get_provider_factories",
    "clear_providers",
]
