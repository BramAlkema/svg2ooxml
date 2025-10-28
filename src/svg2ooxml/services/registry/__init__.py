"""Service registry helpers."""

from __future__ import annotations

from importlib import import_module
from typing import Callable, Dict, Iterable


_PROVIDERS: list[str] = [
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
]

_REGISTRY: Dict[str, Callable[[], object]] = {}
_LOADED: set[str] = set()


def register_provider(name: str, factory: Callable[[], object]) -> None:
    _REGISTRY[name] = factory


def ensure_default_providers(modules: Iterable[str] | None = None) -> None:
    entries = modules or list(_PROVIDERS)
    for name in entries:
        if name in _LOADED:
            continue
        import_module(f"svg2ooxml.services.providers.{name}")
        _LOADED.add(name)


def get_provider_factories() -> Dict[str, Callable[[], object]]:
    ensure_default_providers()
    return dict(_REGISTRY)


__all__ = ["ensure_default_providers", "register_provider", "get_provider_factories"]
