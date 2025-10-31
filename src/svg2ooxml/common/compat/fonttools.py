"""Runtime shims for compatibility with recent fontTools/uharfbuzz APIs."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class _HarfbuzzModule(Protocol):
    """Protocol representing the uharfbuzz module subset we care about."""

    def serialize_with_tag(self, table_tag: str, data: list[Any], obj_list: list[Any]) -> bytes:  # pragma: no cover - imported API
        ...

    def repack_with_tag(self, table_tag: str, data: list[Any], obj_list: list[Any]) -> bytes:  # pragma: no cover - imported API
        ...


def ensure_fonttools_harfbuzz_patch() -> None:
    """
    Ensure fontTools prefers HarfBuzz's ``serialize_with_tag`` helper.

    Newer versions of ``uharfbuzz`` emit a ``DeprecationWarning`` when ``repack_with_tag``
    is used. fontTools has adopted ``serialize_with_tag`` upstream, but the change may not
    be available in the version bundled with the runtime. This shim mirrors that behaviour
    so we stay quiet on current releases without waiting for a dependency bump.
    """

    try:
        from fontTools.ttLib.tables import otBase
    except ImportError:  # pragma: no cover - optional dependency not installed
        return

    hb = getattr(otBase, "hb", None)
    if hb is None:  # pragma: no cover - defensive guard, otBase should expose hb
        try:
            import uharfbuzz as hb_module  # type: ignore[import-not-found]
        except ImportError:  # pragma: no cover - optional dependency not installed
            return
        hb = hb_module

    if not isinstance(hb, _HarfbuzzModule):
        return

    serialize = getattr(hb, "serialize_with_tag", None)
    repack = getattr(hb, "repack_with_tag", None)

    if serialize is None or repack is None:
        return

    if getattr(repack, "__svg2ooxml_patched__", False):
        return

    def _patched(table_tag: Any, data: list[Any], obj_list: list[Any]) -> bytes:
        return serialize(str(table_tag), data, obj_list)

    setattr(_patched, "__svg2ooxml_patched__", True)
    hb.repack_with_tag = _patched  # type: ignore[assignment]
