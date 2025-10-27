"""Huey queue configuration for export jobs."""

from __future__ import annotations

import os
from functools import lru_cache

from huey import MemoryHuey, RedisHuey
from huey.api import Huey

from ..services.export_service import ExportService


@lru_cache(maxsize=1)
def _create_huey() -> Huey:
    """Return a configured Huey instance.

    Prefers Redis when ``REDIS_URL`` is available; otherwise falls back to the
    in-memory backend so unit tests can run without external services.
    """

    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return RedisHuey("svg2ooxml", url=redis_url, results=True)
    return MemoryHuey("svg2ooxml", results=True)


huey: Huey = _create_huey()

# Shared service instance reused by worker tasks.
_export_service = ExportService()


@huey.task(retries=2, retry_delay=60)
def process_export_job(job_id: str) -> None:
    """Huey task that executes an export job."""

    _export_service.process_job(job_id)


def enqueue_export_job(job_id: str) -> None:
    """Schedule an export job for asynchronous processing."""

    huey.enqueue(process_export_job, job_id)
