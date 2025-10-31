"""SVG transform parsing helpers for traversal and IR conversion."""

from __future__ import annotations

from svg2ooxml.common.geometry import Matrix2D, parse_transform_list


class TransformParser:
    """Parse SVG transform strings into :class:`Matrix2D` instances."""

    def parse_to_matrix(self, transform_str: str | None) -> Matrix2D | None:
        if not transform_str or not transform_str.strip():
            return None
        try:
            return parse_transform_list(transform_str.strip())
        except Exception:
            return None


__all__ = ["TransformParser"]
