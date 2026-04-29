"""Policy-related helpers for the IR converter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from svg2ooxml.core.ir.context import IRConverterContext


class PolicyHooksMixin:
    """Mixin providing policy convenience helpers for :class:`IRConverter`."""

    _policy_context = None  # populated by IRConverter

    def _policy_options(self, target: str) -> Mapping[str, Any] | None:
        if self._policy_context is None:
            return None
        return self._policy_context.get(target)

    def _attach_policy_metadata(
        self,
        metadata: dict[str, Any],
        target: str,
        *,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        options = extra if extra is not None else self._policy_options(target)
        if not options:
            return
        policy_meta = metadata.setdefault("policy", {})
        existing = policy_meta.get(target)
        option_dict = dict(options)
        if existing is None:
            policy_meta[target] = option_dict
        else:
            existing.update(option_dict)

    @staticmethod
    def _bitmap_fallback_limits(options: Mapping[str, Any] | None) -> tuple[int | None, int | None]:
        return IRConverterContext.bitmap_fallback_limits(options)


__all__ = ["PolicyHooksMixin"]
