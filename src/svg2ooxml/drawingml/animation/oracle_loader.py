"""Animation oracle index loading."""

from __future__ import annotations

import json
from pathlib import Path

from svg2ooxml.drawingml.animation.oracle_templates import resolve_oracle_child_path
from svg2ooxml.drawingml.animation.oracle_types import OracleSlotError, PresetSlot


class OracleLoaderMixin:
    """Load oracle slot metadata and XML templates from index.json."""

    def _load_index(self, index_path: Path) -> None:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
        slots = raw.get("slots") or {}
        for name, entry in slots.items():
            raw_path = entry.get("path")
            if raw_path is None:
                continue
            try:
                template_path = resolve_oracle_child_path(self._root, raw_path)
            except ValueError as exc:
                raise OracleSlotError(
                    f"Oracle slot '{name}' references unsafe template path {raw_path!r}"
                ) from exc
            if not template_path.is_file():
                raise FileNotFoundError(
                    f"Oracle slot '{name}' references missing template {template_path}"
                )
            slot = PresetSlot(
                name=name,
                path=template_path,
                preset_class=entry["preset_class"],
                preset_id=entry.get("preset_id"),
                preset_subtype=entry.get("preset_subtype"),
                bld_mode=entry.get("bld_mode", "animBg"),
                family_signature=entry["family_signature"],
                content_tokens=tuple(entry.get("content_tokens", [])),
                behavior_tokens=tuple(entry.get("behavior_tokens", [])),
                smil_patterns=tuple(entry.get("smil_patterns", [])),
                source=entry.get("source", ""),
                verification=entry.get("verification", "unknown"),
                notes=entry.get("notes", ""),
            )
            self._index[name] = slot
            self._templates[name] = template_path.read_text(encoding="utf-8")


__all__ = ["OracleLoaderMixin"]
