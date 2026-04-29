"""Filter EMF adapter used by the DrawingML renderer."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from svg2ooxml.common.units import px_to_emu
from svg2ooxml.drawingml.emf_adapter_renderers import EMFAdapterRenderMixin
from svg2ooxml.drawingml.emf_primitives import (
    DEFAULT_FILTER_PALETTE,
    PaletteResolver,
    normalise_value,
    resolve_with_palette,
)
from svg2ooxml.io.emf import EMFBlob


@dataclass(slots=True)
class EMFResult:
    """Container describing a generated EMF asset."""

    emf_bytes: bytes
    relationship_id: str
    width_emu: int
    height_emu: int
    metadata: dict[str, Any]


class EMFAdapter(EMFAdapterRenderMixin):
    """Generate deterministic EMF assets for filter fallbacks."""

    _DEFAULT_SIZE_PX = (96.0, 64.0)

    def __init__(self, *, palette_resolver: PaletteResolver | None = None) -> None:
        self._counter = 0
        self._cache: dict[tuple[str, str], EMFResult] = {}
        self._palette_resolver: PaletteResolver | None = palette_resolver

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_filter(self, filter_type: str, metadata: dict[str, Any] | None = None) -> EMFResult:
        """Return an EMF asset for ``filter_type`` using the supplied metadata."""

        normalised_meta = metadata or {}
        key = self._cache_key(filter_type, normalised_meta)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        if filter_type == "composite":
            result = self._render_composite(normalised_meta)
        elif filter_type == "blend":
            result = self._render_blend(normalised_meta)
        elif filter_type == "component_transfer":
            result = self._render_component_transfer(normalised_meta)
        elif filter_type == "color_matrix":
            result = self._render_color_matrix(normalised_meta)
        elif filter_type == "displacement_map":
            result = self._render_displacement_map(normalised_meta)
        elif filter_type == "turbulence":
            result = self._render_turbulence(normalised_meta)
        elif filter_type == "convolve_matrix":
            result = self._render_convolve_matrix(normalised_meta)
        elif filter_type == "tile":
            result = self._render_tile(normalised_meta)
        elif filter_type == "diffuse_lighting":
            result = self._render_diffuse_lighting(normalised_meta)
        elif filter_type == "specular_lighting":
            result = self._render_specular_lighting(normalised_meta)
        else:
            result = self._render_placeholder(normalised_meta)

        self._cache[key] = result
        return result

    def set_palette_resolver(self, resolver: PaletteResolver | None) -> None:
        """Install a palette resolver that can override filter colours."""

        self._palette_resolver = resolver

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _finalise(self, blob: EMFBlob, metadata: dict[str, Any]) -> EMFResult:
        emf_bytes = blob.finalize()
        width_emu = blob.width_emu
        height_emu = blob.height_emu
        self._counter += 1
        result = EMFResult(
            emf_bytes=emf_bytes,
            relationship_id=f"rIdEmfFilter{self._counter}",
            width_emu=width_emu,
            height_emu=height_emu,
            metadata=dict(metadata),
        )
        return result

    def _size_emu(self) -> tuple[int, int]:
        width_px, height_px = self._DEFAULT_SIZE_PX
        return (max(1, int(round(px_to_emu(width_px)))), max(1, int(round(px_to_emu(height_px)))))

    def _cache_key(self, filter_type: str, metadata: dict[str, Any]) -> tuple[str, str]:
        relevant_keys = (
            "operator",
            "mode",
            "inputs",
            "filter_type",
            "placeholder",
            "scale",
            "x_channel",
            "y_channel",
            "base_frequency_x",
            "base_frequency_y",
            "num_octaves",
            "seed",
            "turbulence_type",
            "stitch_tiles",
            "values",
            "matrix_source",
            "matrix_type",
            "kernel",
            "kernel_unit_length",
            "kernel_source",
            "order",
            "input",
        )
        relevant = {key: metadata.get(key) for key in relevant_keys if key in metadata}
        normalised = repr(normalise_value(relevant))
        digest = hashlib.blake2s(normalised.encode(), digest_size=8).hexdigest()
        return filter_type, digest

    def _color(self, filter_type: str, role: str, default: str, metadata: Mapping[str, Any]) -> str:
        override = resolve_with_palette(self._palette_resolver, filter_type, role, metadata)
        if override:
            return override
        return DEFAULT_FILTER_PALETTE.get(filter_type, {}).get(role, default)


__all__ = ["EMFAdapter", "EMFResult", "PaletteResolver"]
