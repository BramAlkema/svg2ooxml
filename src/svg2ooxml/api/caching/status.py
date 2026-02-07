"""Simple in-memory cache for job status polling."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class _CacheEntry:
    payload: dict[str, Any]
    expires_at: float


class _JobStatusCache:
    def __init__(self, ttl_seconds: float = 5.0) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._store: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if not entry or entry.expires_at < now:
                self._store.pop(key, None)
                return None
            return entry.payload

    def set(self, key: str, value: dict[str, Any]) -> None:
        expires_at = time.time() + self._ttl
        with self._lock:
            self._store[key] = _CacheEntry(payload=value, expires_at=expires_at)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


job_status_cache = _JobStatusCache()


__all__ = ["job_status_cache"]
