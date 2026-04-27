"""Font embedding data contracts."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum


class EmbeddingPermission(Enum):
    """Embedding permissions derived from the OpenType ``fsType`` flags."""

    INSTALLABLE = "installable"
    PREVIEW_PRINT = "preview_print"
    EDITABLE = "editable"
    NO_SUBSETTING = "no_subsetting"
    BITMAP_ONLY = "bitmap_only"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class FontOptimisationLevel(Enum):
    """High level optimisation targets for subsetting."""

    NONE = "none"
    BASIC = "basic"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


@dataclass(frozen=True)
class FontEmbeddingRequest:
    """Parameters supplied by the text pipeline when embedding is desired."""

    font_path: str
    glyph_ids: Sequence[int] = ()
    characters: Sequence[str] = ()
    preserve_hinting: bool = False
    subset_strategy: str = "glyph"
    optimisation: FontOptimisationLevel = FontOptimisationLevel.BALANCED
    preserve_layout_tables: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "glyph_ids", tuple(self.glyph_ids))
        object.__setattr__(self, "characters", tuple(self.characters))


@dataclass(frozen=True)
class FontEmbeddingResult:
    """Result produced by the embedding engine."""

    relationship_id: str | None
    subset_path: str | None
    glyph_count: int
    bytes_written: int
    permission: EmbeddingPermission = EmbeddingPermission.UNKNOWN
    optimisation: FontOptimisationLevel = FontOptimisationLevel.BALANCED
    packaging_metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddedFontPayload:
    """EOT packaging data derived from the subsetted font."""

    subset_bytes: bytes
    eot_bytes: bytes
    guid: uuid.UUID | None
    root_string: str
    style_kind: str
    style_flags: Mapping[str, bool]
    subset_prefix: str | None = None
    charset: int = 1
    panose: bytes = b""
    unicode_ranges: tuple[int, int, int, int] = (0, 0, 0, 0)
    codepage_ranges: tuple[int, int] = (0, 0)
    fs_type: int = 0
    pitch_family: int = 0x32
