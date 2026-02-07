"""Intermediate representation for web font declarations."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass
class FontFaceSrc:
    """Single src descriptor from @font-face rule.

    Represents one source in the src descriptor, e.g.:
        url('font.woff2') format('woff2')
    """

    url: str                    # URL, data URI, or local font name
    format: str | None = None   # 'woff', 'woff2', 'truetype', 'opentype', 'embedded-opentype'
    tech: str | None = None     # Font technology hint (SVG2 spec, rarely used)

    @property
    def is_data_uri(self) -> bool:
        """Check if this is a base64 data URI."""
        return self.url.startswith("data:")

    @property
    def is_remote(self) -> bool:
        """Check if this is a remote HTTP(S) URL."""
        return self.url.startswith(("http://", "https://"))

    @property
    def is_local(self) -> bool:
        """Check if this is a local() font reference."""
        return self.url.startswith("local(") or not (self.is_data_uri or self.is_remote)


@dataclass
class FontFaceRule:
    """Parsed @font-face rule from CSS.

    Represents the complete @font-face declaration:
        @font-face {
            font-family: 'CustomFont';
            src: url('font.woff2') format('woff2'),
                 url('font.woff') format('woff');
            font-weight: 400;
            font-style: normal;
        }
    """

    family: str                          # font-family value (required)
    src: Sequence[FontFaceSrc]           # src descriptors in priority order (required)
    weight: str = "normal"               # font-weight descriptor
    style: str = "normal"                # font-style descriptor
    display: str = "auto"                # font-display strategy
    unicode_range: str | None = None     # unicode-range descriptor

    @property
    def normalized_family(self) -> str:
        """Get normalized family name (lowercase, no quotes)."""
        return self.family.strip('"').strip("'").lower()

    @property
    def weight_numeric(self) -> int:
        """Convert weight to numeric value (100-900).

        Handles string weights like 'bold', numeric strings like '400',
        and normalizes whitespace/decimal inputs per CSS spec.
        """
        return normalize_font_weight(self.weight)


@dataclass(frozen=True)
class SvgFontDefinition:
    """Inline SVG <font> definition extracted from the document."""

    family: str
    svg_data: bytes
    weight: str = "normal"
    style: str = "normal"
    source: str | None = None

    @property
    def normalized_family(self) -> str:
        return self.family.strip('"').strip("'").lower()

    @property
    def weight_numeric(self) -> int:
        return normalize_font_weight(self.weight)


def normalize_font_weight(value: str | None) -> int:
    if value is None:
        return 400

    normalized = value.strip()
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]

    weight_map = {
        "thin": 100,
        "extra-light": 200,
        "ultra-light": 200,
        "light": 300,
        "normal": 400,
        "regular": 400,
        "medium": 500,
        "semi-bold": 600,
        "demi-bold": 600,
        "bold": 700,
        "extra-bold": 800,
        "ultra-bold": 800,
        "black": 900,
        "heavy": 900,
    }

    lower = normalized.lower()
    if lower in weight_map:
        return weight_map[lower]

    try:
        numeric = int(normalized)
        return max(100, min(900, numeric))
    except ValueError:
        return 400
