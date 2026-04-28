"""Compatibility facade for variant expansion and animation rewrite helpers."""

from __future__ import annotations

from svg2ooxml.core.export.variant_grouping import _animation_group_key
from svg2ooxml.core.export.variant_line_endpoints import (
    _compose_simple_line_endpoint_animations,
)
from svg2ooxml.core.export.variant_line_materialization import (
    _materialize_simple_line_paths,
)
from svg2ooxml.core.export.variant_position_motions import (
    _coalesce_simple_position_motions,
)
from svg2ooxml.core.export.variant_trace import _merge_trace_reports

__all__ = [
    "_animation_group_key",
    "_coalesce_simple_position_motions",
    "_compose_simple_line_endpoint_animations",
    "_materialize_simple_line_paths",
    "_merge_trace_reports",
]
