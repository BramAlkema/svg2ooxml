"""Cached colorspacious conversions for the advanced color engine."""

from __future__ import annotations

import threading

import colorspacious
import numpy as np

_conversion_cache = {}
_cache_lock = threading.Lock()


def cached_color_convert(color_value, from_space, to_space):
    """
    Cached color space conversion for performance optimization.

    Args:
        color_value: Color value to convert
        from_space: Source color space
        to_space: Target color space

    Returns:
        Converted color value
    """
    if isinstance(color_value, np.ndarray):
        cache_key = (tuple(color_value), from_space, to_space)
    else:
        cache_key = (color_value, from_space, to_space)

    with _cache_lock:
        if cache_key in _conversion_cache:
            return _conversion_cache[cache_key]

    result = colorspacious.cspace_convert(color_value, from_space, to_space)

    with _cache_lock:
        if len(_conversion_cache) > 1000:
            _conversion_cache.clear()
        _conversion_cache[cache_key] = result

    return result


__all__ = ["cached_color_convert"]
