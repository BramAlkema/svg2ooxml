"""Rich unit conversion facilities shared across the svg2ooxml pipeline."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Final

from .scalars import (
    DEFAULT_DPI,
    EMU_PER_CM,
    EMU_PER_INCH,
    EMU_PER_MM,
    EMU_PER_PICA,
    EMU_PER_POINT,
    EMU_PER_PX_AT_DEFAULT_DPI,
    EMU_PER_Q,
    PX_PER_INCH,
)

_LENGTH_RE: Final = re.compile(
    r"""^\s*
    (?P<number>[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)  # numeric component
    (?P<unit>[a-zA-Z%]*)\s*$
    """,
    re.VERBOSE,
)

_ABSOLUTE_UNIT_FACTORS: Final[Mapping[str, float]] = {
    "px": 1.0,
    "in": PX_PER_INCH,
    "cm": PX_PER_INCH / 2.54,
    "mm": PX_PER_INCH / 25.4,
    "pt": PX_PER_INCH / 72.0,
    "pc": PX_PER_INCH / 6.0,
    "q": PX_PER_INCH / (25.4 * 4.0),
}

_AXIS_ALIASES: Final[Mapping[str, str]] = {
    "x": "width",
    "y": "height",
    "w": "width",
    "h": "height",
    "inline": "width",
    "block": "height",
    "parent-x": "parent_width",
    "parent-y": "parent_height",
    "parent-width": "parent_width",
    "parent-height": "parent_height",
    "vw": "viewport_width",
    "vh": "viewport_height",
    "vmin": "viewport_min",
    "vmax": "viewport_max",
    "font": "font_size",
    "font-size": "font_size",
    "em": "font_size",
    "ex": "font_x_height",
    "ch": "font_x_height",
    "rem": "root_font_size",
}


@dataclass(slots=True, frozen=True)
class ConversionContext:
    """Viewport and font metrics used when resolving relative units."""

    width: float
    height: float
    dpi: float = DEFAULT_DPI
    font_size: float = 12.0
    parent_width: float | None = None
    parent_height: float | None = None
    viewport_width: float | None = None
    viewport_height: float | None = None
    root_font_size: float | None = None
    font_x_height: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "dpi", validate_dpi(self.dpi))

    def derive(
        self,
        *,
        width: float | None = None,
        height: float | None = None,
        font_size: float | None = None,
        dpi: float | None = None,
        viewport_width: float | None = None,
        viewport_height: float | None = None,
        font_x_height: float | None = None,
    ) -> ConversionContext:
        """Create a child context, inheriting the current viewport as parents."""

        return ConversionContext(
            width=width if width is not None else self.width,
            height=height if height is not None else self.height,
            dpi=dpi if dpi is not None else self.dpi,
            font_size=font_size if font_size is not None else self.font_size,
            parent_width=self.width,
            parent_height=self.height,
            viewport_width=viewport_width if viewport_width is not None else self.viewport_width,
            viewport_height=viewport_height if viewport_height is not None else self.viewport_height,
            root_font_size=self.root_font_size if self.root_font_size is not None else self.font_size,
            font_x_height=font_x_height if font_x_height is not None else self.font_x_height,
        )

    def with_root(self, font_size: float | None = None) -> ConversionContext:
        """Return a context with an explicit root font size for rem units."""

        if font_size is None:
            return self if self.root_font_size is not None else replace(self, root_font_size=self.font_size)
        return replace(self, root_font_size=font_size)

    @property
    def viewport_min(self) -> float | None:
        if self.viewport_width is None or self.viewport_height is None:
            return None
        return min(self.viewport_width, self.viewport_height)

    @property
    def viewport_max(self) -> float | None:
        if self.viewport_width is None or self.viewport_height is None:
            return None
        return max(self.viewport_width, self.viewport_height)


class UnitConverter:
    """Convert SVG/CSS length primitives to pixels or EMUs."""

    def __init__(self, *, dpi: float = DEFAULT_DPI, ex_height_ratio: float = 0.5) -> None:
        self.dpi = validate_dpi(dpi)
        self.ex_height_ratio = ex_height_ratio

    # --- public API -----------------------------------------------------

    def create_context(
        self,
        *,
        width: float,
        height: float,
        dpi: float | None = None,
        font_size: float = 12.0,
        parent_width: float | None = None,
        parent_height: float | None = None,
        viewport_width: float | None = None,
        viewport_height: float | None = None,
        root_font_size: float | None = None,
        font_x_height: float | None = None,
    ) -> ConversionContext:
        """Create a conversion context for resolving percentages and relative units."""

        effective_dpi = validate_dpi(dpi if dpi is not None else self.dpi)
        vw = viewport_width if viewport_width is not None else width
        vh = viewport_height if viewport_height is not None else height

        ctx = ConversionContext(
            width=width,
            height=height,
            dpi=effective_dpi,
            font_size=font_size,
            parent_width=parent_width,
            parent_height=parent_height,
            viewport_width=vw,
            viewport_height=vh,
            root_font_size=root_font_size or font_size,
            font_x_height=font_x_height,
        )
        if ctx.font_x_height is None:
            ctx = replace(ctx, font_x_height=font_size * self.ex_height_ratio)
        return ctx

    def to_px(
        self,
        value: str | float | int,
        context: ConversionContext | None = None,
        *,
        axis: str | None = None,
        fallback_unit: str = "px",
    ) -> float:
        """Convert a length string to pixels."""

        number, unit = self._parse_length_value(value, fallback_unit=fallback_unit)

        if unit == "auto":
            raise ValueError("cannot convert 'auto' to pixels")

        if unit in _ABSOLUTE_UNIT_FACTORS:
            px_per_unit = _ABSOLUTE_UNIT_FACTORS[unit]
            px_per_inch = self._dpi(context)
            if unit == "px":
                return number
            # absolute factors above assume PX_PER_INCH. Adjust when dpi differs.
            scale = px_per_inch / PX_PER_INCH
            return number * px_per_unit * scale

        if unit in {"em", "font"}:
            base = self._require_base(context, "font_size", axis or "font_size")
            return number * base

        if unit in {"ex", "ch"}:
            base = self._require_base(context, "font_x_height", axis or "font_x_height")
            return number * base

        if unit == "rem":
            base = self._require_base(context, "root_font_size", axis or "root_font_size")
            return number * base

        if unit in {"vw", "vh", "vmin", "vmax"}:
            alias = _AXIS_ALIASES[unit]
            base = self._require_base(context, alias, axis or alias)
            return number * base / 100.0

        if unit == "%":
            base_name = self._axis_to_base(axis)
            if base_name is None:
                base_name = "width"
            base = self._require_base(context, base_name, axis or base_name)
            return base * number / 100.0

        if unit == "":
            # Unit-less values inherit the fallback unit (px by default).
            fallback = fallback_unit.strip().lower()
            if not fallback or fallback == "px":
                return number
            return self.to_px(f"{number}{fallback}", context, axis=axis, fallback_unit="px")

        raise ValueError(f"Unsupported unit {unit!r}")

    def to_emu(
        self,
        value: str | float | int,
        context: ConversionContext | None = None,
        axis: str | None = None,
        *,
        fallback_unit: str = "px",
    ) -> float:
        """Convert a length to English Metric Units (EMU)."""

        px_value = self.to_px(value, context, axis=axis, fallback_unit=fallback_unit)

        dpi = self._dpi(context)
        inches = px_value / dpi
        return inches * EMU_PER_INCH

    def to_emu_pair(
        self,
        value: tuple[str | float | int, str | float | int],
        context: ConversionContext | None = None,
    ) -> tuple[float, float]:
        """Convert a (x, y) pair into EMUs."""

        return (
            self.to_emu(value[0], context, axis="x"),
            self.to_emu(value[1], context, axis="y"),
        )

    def parse_length(self, value: str | float | int) -> tuple[float, str]:
        """Return the numeric portion and unit suffix for diagnostics."""

        return self._parse_length_value(value)

    # --- helpers --------------------------------------------------------

    def _dpi(self, context: ConversionContext | None) -> float:
        return validate_dpi(context.dpi if context is not None else self.dpi)

    def _parse_length_value(
        self,
        value: str | float | int,
        *,
        fallback_unit: str = "px",
    ) -> tuple[float, str]:
        if isinstance(value, (int, float)):
            return float(value), ""

        token = value.strip()
        if token.lower() == "auto":
            return math.nan, "auto"

        match = _LENGTH_RE.match(token)
        if not match:
            raise ValueError(f"Cannot parse length {value!r}")
        number = float(match.group("number"))
        unit = match.group("unit").lower()
        if unit and unit not in _ABSOLUTE_UNIT_FACTORS and unit not in {
            "%",
            "em",
            "ex",
            "ch",
            "rem",
            "font",
            "vw",
            "vh",
            "vmin",
            "vmax",
        }:
            raise ValueError(f"Unsupported unit {unit!r}")
        if unit == "" and fallback_unit:
            unit = ""
        return number, unit

    def _axis_to_base(self, axis: str | None) -> str | None:
        if axis is None:
            return None
        axis_key = axis.lower()
        return _AXIS_ALIASES.get(axis_key, axis_key if axis_key in {"width", "height"} else None)

    def _require_base(
        self,
        context: ConversionContext | None,
        attribute: str,
        axis: str,
    ) -> float:
        if context is None:
            raise ValueError(f"Relative unit requires context for axis {axis!r}")
        value = getattr(context, attribute)
        if value is None:
            raise ValueError(f"Conversion context lacks required attribute {attribute!r}")
        return value


def px_to_emu(px_value: float, dpi: float = DEFAULT_DPI) -> float:
    """Convenience helper mirroring svg2pptx behaviour."""

    dpi = validate_dpi(dpi)
    inches = px_value / dpi
    return inches * EMU_PER_INCH


def emu_to_px(emu_value: float, dpi: float = DEFAULT_DPI) -> float:
    """Convert EMUs to pixels at the provided DPI."""

    dpi = validate_dpi(dpi)
    inches = emu_value / EMU_PER_INCH
    return inches * dpi


def validate_dpi(dpi: float) -> float:
    try:
        value = float(dpi)
    except (TypeError, ValueError) as exc:
        raise ValueError("dpi must be positive") from exc
    if value <= 0:
        raise ValueError("dpi must be positive")
    return value


_validate_dpi = validate_dpi


def emu_to_unit(emu_value: float, unit: str) -> float:
    """Convert EMU values into a target absolute unit."""

    if unit == "px":
        return emu_value / EMU_PER_PX_AT_DEFAULT_DPI
    if unit == "pt":
        return emu_value / EMU_PER_POINT
    if unit == "cm":
        return emu_value / EMU_PER_CM
    if unit == "mm":
        return emu_value / EMU_PER_MM
    if unit == "pc":
        return emu_value / EMU_PER_PICA
    if unit == "q":
        return emu_value / EMU_PER_Q
    if unit == "in":
        return emu_value / EMU_PER_INCH
    raise ValueError(f"Unsupported target unit {unit!r}")


__all__ = [
    "ConversionContext",
    "UnitConverter",
    "emu_to_px",
    "emu_to_unit",
    "px_to_emu",
    "validate_dpi",
    "DEFAULT_DPI",
    "EMU_PER_CM",
    "EMU_PER_INCH",
    "EMU_PER_MM",
    "EMU_PER_PICA",
    "EMU_PER_POINT",
    "EMU_PER_PX_AT_DEFAULT_DPI",
    "EMU_PER_Q",
]
