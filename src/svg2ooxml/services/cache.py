"""Lightweight cache helpers for conversion-time reuse."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Hashable
from typing import Any


class ConverterCache:
    """Simple LRU cache for conversion helpers.

    The cache is intentionally small and in-memory, mirroring the needs of
    per-document conversion without introducing cross-run state.
    """

    def __init__(self, *, max_entries: int = 1024) -> None:
        self._max_entries = max(1, int(max_entries))
        self._store: OrderedDict[Hashable, Any] = OrderedDict()

    def get(self, key: Hashable, default: Any | None = None) -> Any | None:
        if key in self._store:
            self._store.move_to_end(key)
            return self._store[key]
        return default

    def set(self, key: Hashable, value: Any) -> None:
        self._store[key] = value
        self._store.move_to_end(key)
        if len(self._store) > self._max_entries:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()

    def __contains__(self, key: Hashable) -> bool:
        return key in self._store


__all__ = ["ConverterCache"]
