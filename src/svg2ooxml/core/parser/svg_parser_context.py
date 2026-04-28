"""Runtime context helpers for the public SVG parser."""

from __future__ import annotations

import os
from typing import Any

from svg2ooxml.core.conversion_context import (
    ConversionContextBundle,
    build_conversion_context,
    clone_policy_context,
)
from svg2ooxml.core.parser.preprocess.services import ParserServices
from svg2ooxml.services import ConversionServices


class SVGParserContextMixin:
    def _coerce_context(
        self,
        services: ConversionServices | ParserServices | ConversionContextBundle | None,
    ) -> ConversionContextBundle:
        if services is None:
            return build_conversion_context()
        if isinstance(services, ConversionContextBundle):
            return services.clone()
        if isinstance(services, ParserServices):
            cloned_context = clone_policy_context(services.policy_context)
            if cloned_context is None:
                cloned_context = services.policy_engine.evaluate()
            return build_conversion_context(
                services=services.services,
                policy_engine=services.policy_engine,
                policy_context=cloned_context,
                unit_converter=services.unit_converter,
                style_resolver=services.style_resolver,
            )

        return build_conversion_context(services=services)

    def _register_source_path_resolver(
        self,
        services: Any,
        source_path: str | None,
    ) -> None:
        if not source_path:
            return
        image_service = getattr(services, "image_service", None)
        if not image_service:
            return
        try:
            from svg2ooxml.services.image_service import FileResolver

            base_dir = os.path.dirname(source_path)
            asset_root = self._resolve_asset_root_option(services)
            image_service.register_resolver(
                FileResolver(base_dir, asset_root=asset_root),
                prepend=True,
            )
        except ImportError:
            self._logger.warning(
                "Could not import FileResolver to handle source_path images."
            )

    @staticmethod
    def _resolve_asset_root_option(services: Any) -> str | None:
        resolver = getattr(services, "resolve", None)
        if not callable(resolver):
            return None
        for key in ("asset_root", "root_dir", "source_root"):
            value = resolver(key)
            if isinstance(value, str) and value:
                return value
        return None


__all__ = ["SVGParserContextMixin"]
