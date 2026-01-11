"""Conversion service container."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from svg2ooxml.services.providers.registry import get_provider_factories


@dataclass
class ConversionServices:
    """Lightweight service registry used during parsing and mapping."""

    services: dict[str, Any] = field(default_factory=dict)

    def register(self, name: str, service: Any) -> None:
        self.services[name] = service
        self._bind_if_supported(service)
        self._notify_linked_services(name, service)
        if name == "policy_engine":
            self._propagate_policy_engine(service)

    def resolve(self, name: str, default: Any = None) -> Any:
        return self.services.get(name, default)

    def clone(self) -> "ConversionServices":
        """Return a shallow clone with cloned services when supported."""
        cloned = ConversionServices()
        for name, value in self.services.items():
            cloned.register(name, self._clone_value(value))
        return cloned

    def ensure_default(self, name: str) -> Any:
        if name not in self.services:
            factory_map = get_provider_factories()
            factory = factory_map.get(name)
            if factory is not None:
                self.register(name, factory())
        return self.services.get(name)

    @property
    def filter_service(self) -> Any:
        return self.resolve("filter")

    @property
    def gradient_service(self) -> Any:
        return self.resolve("gradient")

    @property
    def pattern_service(self) -> Any:
        return self.resolve("pattern")

    @property
    def marker_service(self) -> Any:
        return self.resolve("marker")

    @property
    def symbol_service(self) -> Any:
        return self.resolve("symbol")

    @property
    def image_service(self) -> Any:
        return self.resolve("image")

    @property
    def color_space_service(self) -> Any:
        return self.resolve("color_space")

    @property
    def font_service(self) -> Any:
        return self.resolve("font")

    @property
    def font_embedding_engine(self) -> Any:
        return self.resolve("font_embedding")

    @property
    def hyperlink_processor(self) -> Any:
        return self.resolve("hyperlink_processor")

    @property
    def smart_font_converter(self) -> Any:
        return self.resolve("smart_font_converter")

    @property
    def policy_engine(self) -> Any:
        return self.resolve("policy_engine")

    @property
    def mask_service(self) -> Any:
        return self.resolve("mask_service")

    @property
    def mask_processor(self) -> Any:
        return self.resolve("mask_processor")

    @property
    def emf_path_adapter(self) -> Any:
        return self.resolve("emf_path_adapter")

    @property
    def mask_asset_store(self) -> Any:
        return self.resolve("mask_asset_store")

    @property
    def mask_assets(self) -> Any:
        return self.resolve("mask_asset_store")

    @property
    def clip_service(self) -> Any:
        return self.resolve("clip_service")

    @property
    def drawingml_path_generator(self) -> Any:
        return self.resolve("drawingml_path_generator")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _bind_if_supported(self, service: Any) -> None:
        if hasattr(service, "bind_services"):
            service.bind_services(self)

    def _notify_linked_services(self, name: str, value: Any) -> None:
        link_map = {
            "filters": "filter",
            "gradients": "gradient",
            "patterns": "pattern",
            "markers": "marker",
            "symbols": "symbol",
        }
        target_name = link_map.get(name)
        if not target_name:
            return
        target = self.resolve(target_name)
        if target and hasattr(target, "update_definitions"):
            target.update_definitions(value)

    def _clone_value(self, value: Any) -> Any:
        if hasattr(value, "clone"):
            return value.clone()
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list):
            return list(value)
        return value

    def _propagate_policy_engine(self, engine: Any) -> None:
        for service in self.services.values():
            if service is engine:
                continue
            setter = getattr(service, "set_policy_engine", None)
            if callable(setter):
                setter(engine)


__all__ = ["ConversionServices"]
