"""Fallback filter service when optional render dependencies are missing."""

from __future__ import annotations

import logging
from typing import Any

from svg2ooxml.services.filter_types import FilterEffectResult


class DisabledFilterService:
    """Minimal filter service that reports EMF fallback when filters are disabled."""

    def __init__(self, *, logger: logging.Logger | None = None, reason: str | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._reason = reason or "optional_dependency_missing"
        self._warned = False

    def bind_services(self, _services: Any) -> None:  # pragma: no cover - no-op
        return

    def clone(self) -> DisabledFilterService:
        return DisabledFilterService(logger=self._logger, reason=self._reason)

    def set_strategy(self, _strategy: str) -> None:  # pragma: no cover - no-op
        return

    def update_definitions(self, _filters: Any | None) -> None:  # pragma: no cover - no-op
        return

    def register_filter(self, _filter_id: str, _definition: Any) -> None:  # pragma: no cover - no-op
        return

    def get_filter_content(self, _filter_id: str, *, context: Any | None = None) -> str | None:  # noqa: ARG002
        return None

    @property
    def runtime_capability(self) -> str:
        return "disabled"

    def resolve_effects(self, filter_ref: str, *, context: Any | None = None) -> list[FilterEffectResult]:
        if not self._warned:
            self._logger.warning(
                "Filter rendering disabled (%s). Install svg2ooxml[render] for full filter support.",
                self._reason,
            )
            self._warned = True
        metadata = {
            "filter_id": filter_ref,
            "disabled": True,
            "reason": self._reason,
            "fallback": "emf",
            "runtime_capability": self.runtime_capability,
        }
        return [
            FilterEffectResult(
                effect=None,
                strategy="emf",
                fallback="emf",
                metadata=metadata,
            )
        ]


__all__ = ["DisabledFilterService"]
