"""Lazy animation oracle vocabulary accessors."""

from __future__ import annotations

from svg2ooxml.drawingml.animation.oracle_types import OracleSlotError
from svg2ooxml.drawingml.animation.oracle_vocabulary import (
    AttrNameEntry,
    DeadPath,
    FilterEntry,
    load_attrname_vocabulary,
    load_dead_paths,
    load_filter_vocabulary,
)


class OracleVocabularyMixin:
    """Expose cached filter, attrName, and dead-path SSOT vocabularies."""

    def filter_vocabulary(self) -> tuple[FilterEntry, ...]:
        """Return the complete animEffect filter vocabulary SSOT."""
        if self._filter_vocabulary is None:
            self._filter_vocabulary = load_filter_vocabulary(self._root)
            self._filter_by_value = {
                entry.value: entry for entry in self._filter_vocabulary
            }
        return self._filter_vocabulary

    def filter_entry(self, value: str) -> FilterEntry:
        """Look up a :class:`FilterEntry` by its ``value`` field."""
        self.filter_vocabulary()
        if self._filter_by_value is not None and value in self._filter_by_value:
            return self._filter_by_value[value]
        raise OracleSlotError(f"Unknown filter vocabulary value: {value!r}")

    def attrname_vocabulary(self) -> tuple[AttrNameEntry, ...]:
        """Return the complete <p:attrName> vocabulary SSOT."""
        if self._attrname_vocabulary is None:
            self._attrname_vocabulary = load_attrname_vocabulary(self._root)
            self._attrname_by_value = {
                entry.value: entry for entry in self._attrname_vocabulary
            }
        return self._attrname_vocabulary

    def attrname_entry(self, value: str) -> AttrNameEntry:
        """Look up an :class:`AttrNameEntry` by its ``value`` field."""
        self.attrname_vocabulary()
        if self._attrname_by_value is not None and value in self._attrname_by_value:
            return self._attrname_by_value[value]
        raise OracleSlotError(f"Unknown attrName vocabulary value: {value!r}")

    def is_valid_attrname(self, value: str) -> bool:
        """True if *value* appears in the attrName vocabulary SSOT."""
        self.attrname_vocabulary()
        return self._attrname_by_value is not None and value in self._attrname_by_value

    def dead_paths(self) -> tuple[DeadPath, ...]:
        """Return the empirically-falsified animation shape catalog."""
        if self._dead_paths is None:
            self._dead_paths = load_dead_paths(self._root)
            self._dead_path_by_id = {entry.id: entry for entry in self._dead_paths}
        return self._dead_paths

    def dead_path(self, id: str) -> DeadPath:
        """Look up a :class:`DeadPath` by its ``id`` attribute."""
        self.dead_paths()
        if self._dead_path_by_id is not None and id in self._dead_path_by_id:
            return self._dead_path_by_id[id]
        raise OracleSlotError(f"Unknown dead path id: {id!r}")


__all__ = ["OracleVocabularyMixin"]
