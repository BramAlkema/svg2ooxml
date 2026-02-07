"""Simple conversion pipeline descriptor used by the CLI converter."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

DEFAULT_STAGE_NAMES: tuple[str, ...] = (
    'parse_svg',
    'build_scene',
    'write_package',
)


@dataclass(frozen=True)
class ConversionPipeline:
    """Lightweight pipeline descriptor for the CLI converter."""

    stages: tuple[str, ...] = DEFAULT_STAGE_NAMES

    def describe_stage_names(self) -> Iterable[str]:
        return self.stages


__all__ = ['ConversionPipeline', 'DEFAULT_STAGE_NAMES']
