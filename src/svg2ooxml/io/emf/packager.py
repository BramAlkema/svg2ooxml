"""Relationship and packaging helpers for EMF media."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple


@dataclass(frozen=True)
class EMFMedia:
    """Persisted EMF payload with packaging metadata."""

    relationship_id: str
    filename: str
    data: bytes
    width_emu: int | None = None
    height_emu: int | None = None


class EMFRelationshipManager:
    """Deduplicates EMF blobs and tracks their relationship identifiers."""

    def __init__(self) -> None:
        self._hash_to_entry: Dict[str, EMFMedia] = {}
        self._rel_to_entry: Dict[str, EMFMedia] = {}
        self._next_id = 1

    def reset(self) -> None:
        """Forget all registered media."""

        self._hash_to_entry.clear()
        self._rel_to_entry.clear()
        self._next_id = 1

    def register(
        self,
        emf_bytes: bytes,
        *,
        rel_id: str | None = None,
        width_emu: int | None = None,
        height_emu: int | None = None,
    ) -> Tuple[EMFMedia, bool]:
        """Register an EMF payload, returning (entry, is_new)."""

        digest = hashlib.md5(emf_bytes, usedforsecurity=False).hexdigest()
        existing = self._hash_to_entry.get(digest)
        if existing:
            if existing.width_emu is None and width_emu is not None:
                # Update cached dimensions if first entry had none.
                updated = EMFMedia(
                    relationship_id=existing.relationship_id,
                    filename=existing.filename,
                    data=existing.data,
                    width_emu=width_emu,
                    height_emu=height_emu,
                )
                self._hash_to_entry[digest] = updated
                self._rel_to_entry[existing.relationship_id] = updated
                existing = updated
            return existing, False

        relationship_id = self._allocate_rel_id(rel_id)
        size_suffix = ""
        if width_emu is not None and height_emu is not None:
            size_suffix = f"_{width_emu}x{height_emu}"
        entry = EMFMedia(
            relationship_id=relationship_id,
            filename=f"emf_{digest[:8]}{size_suffix}.emf",
            data=emf_bytes,
            width_emu=width_emu,
            height_emu=height_emu,
        )
        self._hash_to_entry[digest] = entry
        self._rel_to_entry[relationship_id] = entry
        return entry, True

    def get(self, relationship_id: str) -> EMFMedia | None:
        """Return the registered media for the supplied relationship id."""

        return self._rel_to_entry.get(relationship_id)

    def items(self) -> Iterable[EMFMedia]:
        """Iterate the unique registered media entries."""

        return self._hash_to_entry.values()

    def _allocate_rel_id(self, preferred: str | None) -> str:
        if preferred and preferred not in self._rel_to_entry:
            return preferred
        while True:
            candidate = f"rIdEmf{self._next_id}"
            self._next_id += 1
            if candidate not in self._rel_to_entry:
                return candidate


__all__ = ["EMFMedia", "EMFRelationshipManager"]
