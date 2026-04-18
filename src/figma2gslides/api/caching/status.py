"""Small in-memory cache for export job status snapshots."""

from __future__ import annotations


class _JobStatusCache:
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    def get(self, job_id: str):
        return self._store.get(job_id)

    def set(self, job_id: str, payload: dict) -> None:
        self._store[job_id] = dict(payload)

    def invalidate(self, job_id: str) -> None:
        self._store.pop(job_id, None)


job_status_cache = _JobStatusCache()

__all__ = ["job_status_cache"]
