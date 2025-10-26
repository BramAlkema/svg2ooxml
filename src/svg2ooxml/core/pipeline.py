"""Minimal pipeline scaffolding used to seed the svg2ooxml project."""

from __future__ import annotations

from collections.abc import Iterable

DEFAULT_STAGE_NAMES: tuple[str, ...] = (
    "parse_svg",
    "map_shapes",
    "apply_policy",
    "write_package",
)


class ConversionPipeline:
    """Simple placeholder pipeline exposing the canonical stage order."""

    def __init__(self, stage_names: Iterable[str] | None = None) -> None:
        self._stage_names: tuple[str, ...] = tuple(stage_names or DEFAULT_STAGE_NAMES)

    @property
    def stages(self) -> tuple[str, ...]:
        """Return the configured stage names."""
        return self._stage_names

    def describe_stage_names(self) -> tuple[str, ...]:
        """Return the ordered list of stage identifiers."""
        return self._stage_names


__all__ = ["ConversionPipeline", "DEFAULT_STAGE_NAMES"]
