"""Simple conversion pipeline descriptor used by the CLI converter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

DEFAULT_STAGE_NAMES: Tuple[str, ...] = (
    'parse_svg',
    'build_scene',
    'write_package',
)


@dataclass(frozen=True)
class ConversionPipeline:
    """Lightweight pipeline descriptor for the CLI converter."""

    stages: Tuple[str, ...] = DEFAULT_STAGE_NAMES

    def describe_stage_names(self) -> Iterable[str]:
        return self.stages


__all__ = ['ConversionPipeline', 'DEFAULT_STAGE_NAMES']
