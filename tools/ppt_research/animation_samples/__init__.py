"""Hand-built minimal animation sample PPTXs for interactive tuning.

Each sample module exposes ``NAME``, ``DURATION_S`` (slideshow capture hint),
and ``build(output_path: Path) -> Path`` which writes a minimal presentation
exercising one animation effect.

Samples are consumed by :mod:`tools.ppt_research.animation_tune` together with
:class:`tools.ppt_research.pptx_session.PptxSession` to drive a fast edit/reload
iteration loop against Microsoft PowerPoint on macOS.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Protocol


class SampleModule(Protocol):
    NAME: str
    DURATION_S: float

    def build(self, output_path: Path) -> Path: ...  # pragma: no cover - protocol


_REGISTRY: dict[str, str] = {
    "fade_in": "tools.ppt_research.animation_samples.fade_in",
    "exit_fade": "tools.ppt_research.animation_samples.exit_fade",
    "appear_visible": "tools.ppt_research.animation_samples.appear_visible",
    "color_change": "tools.ppt_research.animation_samples.color_change",
    "rotate_spin": "tools.ppt_research.animation_samples.rotate_spin",
    "scale_grow": "tools.ppt_research.animation_samples.scale_grow",
    "motion_translate": "tools.ppt_research.animation_samples.motion_translate",
}


def available_samples() -> list[str]:
    """Return registered sample names."""
    return sorted(_REGISTRY)


def load_sample(name: str) -> SampleModule:
    """Import and return the sample module for *name*."""
    try:
        dotted = _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"Unknown sample '{name}'. Available: {', '.join(available_samples())}"
        ) from exc
    module = import_module(dotted)
    for attr in ("NAME", "DURATION_S", "build"):
        if not hasattr(module, attr):
            raise AttributeError(f"Sample '{name}' is missing required attribute '{attr}'")
    return module  # type: ignore[return-value]


def build_sample(name: str, output_path: Path) -> Path:
    """Build *name* to *output_path* and return the written file."""
    module = load_sample(name)
    return module.build(output_path)


__all__ = [
    "SampleModule",
    "available_samples",
    "build_sample",
    "load_sample",
]
