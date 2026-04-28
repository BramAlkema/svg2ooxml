"""SVG path data parser producing IR geometry segments."""

from __future__ import annotations

from functools import lru_cache

from svg2ooxml.common.geometry.paths.parser_engine import _parse_path_data
from svg2ooxml.common.geometry.paths.parser_types import (
    _MAX_CACHED_PATH_CHARS,
    PathParseError,
)
from svg2ooxml.ir.geometry import SegmentType


def parse_path_data(data: str) -> list[SegmentType]:
    """Parse SVG path ``d`` strings into IR segments."""

    if len(data) > _MAX_CACHED_PATH_CHARS:
        return list(_parse_path_data(data))
    return list(_parse_path_data_cached(data))


@lru_cache(maxsize=2048)
def _parse_path_data_cached(data: str) -> tuple[SegmentType, ...]:
    return _parse_path_data(data)


__all__ = ["PathParseError", "parse_path_data"]
