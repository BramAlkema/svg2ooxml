"""Simple color data structures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Color:
    r: float
    g: float
    b: float
    a: float = 1.0

    def clamp(self) -> Color:
        return Color(
            max(0.0, min(1.0, self.r)),
            max(0.0, min(1.0, self.g)),
            max(0.0, min(1.0, self.b)),
            max(0.0, min(1.0, self.a)),
        )

    def to_hex(self, *, include_alpha: bool = False) -> str:
        r = round(self._clamped(self.r) * 255)
        g = round(self._clamped(self.g) * 255)
        b = round(self._clamped(self.b) * 255)
        if include_alpha:
            a = round(self._clamped(self.a) * 255)
            return f"#{r:02x}{g:02x}{b:02x}{a:02x}"
        return f"#{r:02x}{g:02x}{b:02x}"

    def with_alpha(self, alpha: float) -> Color:
        return Color(self.r, self.g, self.b, alpha)

    def to_oklab(self) -> tuple[float, float, float]:
        from .oklab import rgb_to_oklab

        return rgb_to_oklab(self._clamped(self.r), self._clamped(self.g), self._clamped(self.b))

    def to_oklch(self) -> tuple[float, float, float]:
        from .oklab import rgb_to_oklch

        return rgb_to_oklch(self._clamped(self.r), self._clamped(self.g), self._clamped(self.b))

    @classmethod
    def from_oklab(cls, l: float, a: float, b: float, alpha: float = 1.0) -> Color:  # noqa: E741 -- OKLab spec notation for lightness
        from .oklab import oklab_to_rgb

        r, g, b = oklab_to_rgb(l, a, b)
        return cls(r, g, b, alpha).clamp()

    @classmethod
    def from_oklch(cls, l: float, c: float, h: float, alpha: float = 1.0) -> Color:  # noqa: E741 -- OKLCh spec notation for lightness
        from .oklab import oklch_to_rgb

        r, g, b = oklch_to_rgb(l, c, h)
        return cls(r, g, b, alpha).clamp()

    @staticmethod
    def _clamped(component: float) -> float:
        return max(0.0, min(1.0, component))


TRANSPARENT = Color(0.0, 0.0, 0.0, 0.0)

__all__ = ["Color", "TRANSPARENT"]
