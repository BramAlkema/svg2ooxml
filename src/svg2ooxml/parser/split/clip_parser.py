"""Legacy clip-path extractor shim.

The original svg2pptx parser exposed :class:`ClipPathExtractor` and
`ClipDefinition`. The resvg-backed pipeline supersedes that extractor, so we
keep a stub that points callers at the new clipmask layer while maintaining the
old import surface.  Any direct use should migrate to the resvg collector in
``svg2ooxml.map.converter.resvg_clip_mask``.
"""

from __future__ import annotations

from svg2ooxml.clipmask.types import ClipDefinition


class ClipPathExtractor:  # pragma: no cover - maintained for backwards compat only
    """Legacy stub signalling removal of the old clip extractor."""

    def __init__(self, *args, **kwargs) -> None:  # noqa: D401 - compatibility shim
        raise NotImplementedError(
            "clip_extractor has been removed; use resvg-based clip collection via"
            " svg2ooxml.map.converter.resvg_clip_mask.collect_resvg_clip_definitions instead."
        )


__all__ = ["ClipPathExtractor", "ClipDefinition"]
