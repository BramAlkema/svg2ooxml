"""Office profile constants and validation helpers."""

from __future__ import annotations

OFFICE_PROFILE_ECMA_STRICT = "ecma_strict"
OFFICE_PROFILE_COMPAT = "office_compat"

ALLOWED_OFFICE_PROFILES = frozenset(
    {
        OFFICE_PROFILE_ECMA_STRICT,
        OFFICE_PROFILE_COMPAT,
    }
)

NS_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
NS_A14 = "http://schemas.microsoft.com/office/drawing/2010/main"
NS_ASVG = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
NS_P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"

# DrawingML / Picture extension URIs.
EXT_URI_USE_LOCAL_DPI = "{28A0092B-C50C-407E-A947-70E740481C1C}"
EXT_URI_SVG_BLIP = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"

# Presentation properties extension URIs.
EXT_URI_DISCARD_IMAGE_EDIT_DATA = "{E76CE94A-603C-4142-B9EB-6D1370010A27}"
EXT_URI_DEFAULT_IMAGE_DPI = "{D31A062A-798A-4329-ABDD-BBA856620510}"

# Office-compatible defaults observed in PowerPoint.
DEFAULT_IMAGE_DPI_VALUE = 220
USE_LOCAL_DPI_VALUE = 0
DISCARD_IMAGE_EDIT_DATA_VALUE = 0


def normalize_office_profile(profile: str | None) -> str:
    """Return a canonical office profile token or raise ValueError."""

    value = (profile or OFFICE_PROFILE_ECMA_STRICT).strip().lower()
    if value not in ALLOWED_OFFICE_PROFILES:
        raise ValueError(
            f"Invalid office_profile: {profile!r}. "
            f"Must be one of {sorted(ALLOWED_OFFICE_PROFILES)}."
        )
    return value


__all__ = [
    "ALLOWED_OFFICE_PROFILES",
    "DEFAULT_IMAGE_DPI_VALUE",
    "DISCARD_IMAGE_EDIT_DATA_VALUE",
    "EXT_URI_DEFAULT_IMAGE_DPI",
    "EXT_URI_DISCARD_IMAGE_EDIT_DATA",
    "EXT_URI_SVG_BLIP",
    "EXT_URI_USE_LOCAL_DPI",
    "NS_A14",
    "NS_ASVG",
    "NS_MC",
    "NS_P14",
    "OFFICE_PROFILE_COMPAT",
    "OFFICE_PROFILE_ECMA_STRICT",
    "USE_LOCAL_DPI_VALUE",
    "normalize_office_profile",
]
