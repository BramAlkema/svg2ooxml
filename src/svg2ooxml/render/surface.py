"""Surface abstraction backed by skia-python."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:  # pragma: no cover - optional dependency guard
    import skia
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("svg2ooxml.render requires skia-python; install the 'render' extra.") from exc


@dataclass(slots=True)
class Surface:
    """Wrapper around a skia.Surface with convenience helpers."""

    _surface: skia.Surface
    width: int
    height: int
    scale: float = 1.0

    @classmethod
    def make(cls, width: int, height: int, *, scale: float = 1.0) -> "Surface":
        surface = skia.Surface(int(max(width, 1) * scale), int(max(height, 1) * scale))
        return cls(surface, width, height, scale=scale)

    def canvas(self) -> skia.Canvas:
        return self._surface.getCanvas()

    def snapshot_rgba(self) -> np.ndarray:
        """Return RGBA buffer as a NumPy array."""

        image = self._surface.makeImageSnapshot()
        width_px = max(1, int(self.width * self.scale))
        height_px = max(1, int(self.height * self.scale))
        buffer = image.tobytes()
        arr = np.frombuffer(buffer, dtype=np.uint8)
        return arr.reshape((height_px, width_px, 4))


__all__ = ["Surface"]
