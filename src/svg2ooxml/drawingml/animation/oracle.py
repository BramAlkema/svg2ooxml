"""Animation oracle template loader and public facade."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from svg2ooxml.drawingml.animation.evidence import EvidenceTier as EvidenceTier
from svg2ooxml.drawingml.animation.oracle_compound import OracleCompoundMixin
from svg2ooxml.drawingml.animation.oracle_fragments import OracleFragmentMixin
from svg2ooxml.drawingml.animation.oracle_instantiation import (
    OracleInstantiationMixin,
)
from svg2ooxml.drawingml.animation.oracle_loader import OracleLoaderMixin
from svg2ooxml.drawingml.animation.oracle_types import (
    _BUILD_MODE_ATTR as _BUILD_MODE_ATTR,
)
from svg2ooxml.drawingml.animation.oracle_types import (
    NS_A as NS_A,
)
from svg2ooxml.drawingml.animation.oracle_types import (
    BehaviorFragment as BehaviorFragment,
)
from svg2ooxml.drawingml.animation.oracle_types import (
    OracleSlotError as OracleSlotError,
)
from svg2ooxml.drawingml.animation.oracle_types import (
    PresetSlot as PresetSlot,
)
from svg2ooxml.drawingml.animation.oracle_types import (
    _default_root,
)
from svg2ooxml.drawingml.animation.oracle_vocabulary import (
    AttrNameEntry as AttrNameEntry,
)
from svg2ooxml.drawingml.animation.oracle_vocabulary import (
    DeadPath as DeadPath,
)
from svg2ooxml.drawingml.animation.oracle_vocabulary import (
    FilterEntry as FilterEntry,
)
from svg2ooxml.drawingml.animation.oracle_vocabulary_access import (
    OracleVocabularyMixin,
)

__all__ = [
    "AnimationOracle",
    "AttrNameEntry",
    "BehaviorFragment",
    "DeadPath",
    "EvidenceTier",
    "FilterEntry",
    "OracleSlotError",
    "PresetSlot",
    "default_oracle",
]


class AnimationOracle(
    OracleLoaderMixin,
    OracleVocabularyMixin,
    OracleInstantiationMixin,
    OracleFragmentMixin,
    OracleCompoundMixin,
):
    """In-memory view over the parameterised oracle templates."""

    def __init__(self, root: Path | str | None = None) -> None:
        self._root = Path(root) if root is not None else _default_root()
        if not self._root.is_dir():
            raise FileNotFoundError(f"Animation oracle root not found: {self._root}")
        index_path = self._root / "index.json"
        if not index_path.is_file():
            raise FileNotFoundError(f"Animation oracle index missing: {index_path}")
        self._index: dict[str, PresetSlot] = {}
        self._templates: dict[str, str] = {}
        self._filter_vocabulary: tuple[FilterEntry, ...] | None = None
        self._filter_by_value: dict[str, FilterEntry] | None = None
        self._attrname_vocabulary: tuple[AttrNameEntry, ...] | None = None
        self._attrname_by_value: dict[str, AttrNameEntry] | None = None
        self._dead_paths: tuple[DeadPath, ...] | None = None
        self._dead_path_by_id: dict[str, DeadPath] | None = None
        self._load_index(index_path)

    @property
    def root(self) -> Path:
        return self._root

    def slots(self) -> list[PresetSlot]:
        return list(self._index.values())

    def slot(self, name: str) -> PresetSlot:
        try:
            return self._index[name]
        except KeyError as exc:
            raise OracleSlotError(name) from exc

    def template_text(self, name: str) -> str:
        if name not in self._templates:
            raise OracleSlotError(name)
        return self._templates[name]


@lru_cache(maxsize=1)
def default_oracle() -> AnimationOracle:
    """Return a process-wide cached :class:`AnimationOracle` instance."""
    return AnimationOracle()
