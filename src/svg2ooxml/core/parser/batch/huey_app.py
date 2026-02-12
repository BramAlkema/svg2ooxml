"""Huey configuration for parser batch jobs."""

from __future__ import annotations

import os
from pathlib import Path

from huey import RedisHuey, SqliteHuey
from huey.api import Huey

from svg2ooxml.common.tempfiles import project_temp_dir


def _sqlite_path() -> Path:
    configured = os.getenv("SVG2OOXML_HUEY_DB")
    if configured:
        return Path(configured).expanduser()
    return project_temp_dir() / "svg2ooxml_batch_huey.db"


def _create_huey() -> Huey:
    """Return a configured Huey instance for batch conversions.

    Prefers Redis when available; falls back to SqliteHuey for local workflows.
    """

    redis_url = os.getenv("SVG2OOXML_BATCH_REDIS_URL") or os.getenv("REDIS_URL")
    if redis_url:
        return RedisHuey("svg2ooxml-batch", url=redis_url, results=True)

    sqlite_path = _sqlite_path()
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteHuey("svg2ooxml-batch", filename=str(sqlite_path), results=True)


huey: Huey = _create_huey()

__all__ = ["huey"]
