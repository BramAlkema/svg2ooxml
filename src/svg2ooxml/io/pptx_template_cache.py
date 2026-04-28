"""Small in-process cache for immutable PPTX scaffold files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_TemplateSignature = tuple[tuple[str, int, int], ...]
_TemplateEntry = tuple[str, bytes]


def copy_template_tree(source_root: Path, target_root: Path) -> None:
    """Materialize a cached template tree under ``target_root``.

    The PPTX scaffold is package data and normally immutable for the process.
    We still key the cache by file size and mtime so editable installs pick up
    template changes during development.
    """

    for relative_name, data in load_template_entries(source_root):
        target = target_root / relative_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def load_template_entries(source_root: Path) -> tuple[_TemplateEntry, ...]:
    """Return cached ``(relative_name, data)`` entries for a template tree."""

    source_root = source_root.resolve()
    return _cached_template_entries(str(source_root), _template_signature(source_root))


def _template_signature(root: Path) -> _TemplateSignature:
    entries: list[tuple[str, int, int]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        entries.append(
            (
                path.relative_to(root).as_posix(),
                stat.st_mtime_ns,
                stat.st_size,
            )
        )
    return tuple(entries)


@lru_cache(maxsize=8)
def _cached_template_entries(
    root_name: str,
    signature: _TemplateSignature,
) -> tuple[_TemplateEntry, ...]:
    root = Path(root_name)
    return tuple(
        (relative_name, (root / relative_name).read_bytes())
        for relative_name, _, _ in signature
    )


__all__ = ["copy_template_tree", "load_template_entries"]
