"""Font embedding engine with basic subsetting support."""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha1
from pathlib import Path
from typing import Iterable, Mapping, Sequence
import uuid

from svg2ooxml.common.tempfiles import project_temp_dir
from svg2ooxml.services.fonts.eot import build_eot, EOTConversionError

try:  # pragma: no cover - optional dependency
    from fontTools import subset as fonttools_subset
    from fontTools.ttLib import TTFont
except Exception:  # pragma: no cover - environments without fontTools
    fonttools_subset = None  # type: ignore[assignment]
    TTFont = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


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


class FontEmbeddingEngine:
    """Subset fonts using fontTools when available and track simple stats."""

    def __init__(self) -> None:
        self._stats: dict[str, int] = {
            "subset_requests": 0,
            "subset_success": 0,
            "subset_failures": 0,
            "subset_cache_hits": 0,
            "bytes_total": 0,
            "packaged_fonts": 0,
            "packaged_bytes": 0,
            "permission_denied": 0,
            "bitmap_only": 0,
        }
        self._cache: dict[str, FontEmbeddingResult] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def can_embed(self, font_path: str) -> bool:
        """Return whether the font can be embedded (basic fsType inspection)."""

        permission = self._read_embedding_permission(font_path)
        return permission not in {EmbeddingPermission.RESTRICTED, EmbeddingPermission.UNKNOWN}

    def subset_font(self, request: FontEmbeddingRequest) -> FontEmbeddingResult | None:
        """Produce (or reuse) a subsetted font for the given glyph set."""

        self._stats["subset_requests"] += 1
        cache_key = self._cache_key(request)
        if cache_key in self._cache:
            self._stats["subset_cache_hits"] += 1
            return self._cache[cache_key]

        text_payload = self._prepare_subset_text(request)
        if not text_payload:
            logger.debug("No glyphs or characters provided for embedding; skipping subset generation.")
            self._stats["subset_failures"] += 1
            return None

        permission = self._read_embedding_permission(request.font_path)
        if not isinstance(permission, EmbeddingPermission):
            if isinstance(permission, str) and permission in EmbeddingPermission._value2member_map_:
                permission = EmbeddingPermission(permission)
            else:
                permission = EmbeddingPermission.UNKNOWN
        if permission == EmbeddingPermission.RESTRICTED:
            logger.info("Font %s prohibits embedding (fsType restricted)", request.font_path)
            self._stats["permission_denied"] += 1
            self._stats["subset_failures"] += 1
            return None
        if permission == EmbeddingPermission.BITMAP_ONLY:
            self._stats["bitmap_only"] += 1

        strategy = (request.subset_strategy or "glyph").lower()
        if permission == EmbeddingPermission.NO_SUBSETTING and strategy != "none":
            logger.debug("Font %s forbids subsetting; switching to copy", request.font_path)
            strategy = "none"
        if permission == EmbeddingPermission.BITMAP_ONLY and strategy != "none":
            logger.debug("Font %s allows bitmap-only embedding; switching to copy", request.font_path)
            strategy = "none"

        if strategy == "none":
            result = self._subset_copy(request, permission)
        else:
            result = self._subset_with_fonttools(request, text_payload, permission)

        if result is None:
            self._stats["subset_failures"] += 1
            return None

        self._stats["subset_success"] += 1
        self._stats["bytes_total"] += max(0, result.bytes_written)
        self._cache[cache_key] = result
        return result

    def record_packaged_font(self, relationship_id: str | None, size_bytes: int) -> None:
        self._stats["packaged_fonts"] += 1
        self._stats["packaged_bytes"] += max(size_bytes, 0)

    def stats(self) -> Mapping[str, int]:
        return dict(self._stats)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _subset_copy(
        self,
        request: FontEmbeddingRequest,
        permission: EmbeddingPermission,
    ) -> FontEmbeddingResult | None:
        # Check if font data is already loaded (e.g., from web fonts)
        if "font_data" in request.metadata:
            data = request.metadata["font_data"]
            if not isinstance(data, bytes):
                logger.debug("Invalid font_data type in metadata: %s", type(data))
                return None
        else:
            # Fall back to reading from filesystem
            try:
                data = Path(request.font_path).read_bytes()
            except OSError as exc:  # pragma: no cover - depends on local filesystem
                logger.debug("Failed to read font for direct embedding: %s", exc)
                return None

        metadata = {
            "subset_strategy": request.subset_strategy,
            "preserve_hinting": request.preserve_hinting,
            "font_path": request.font_path,
            "glyph_ids": request.glyph_ids,
            "characters": request.characters,
            "font_data": data,
            "optimisation": request.optimisation.value,
            "permission": permission.value,
        }
        metadata.update(request.metadata)

        return FontEmbeddingResult(
            relationship_id=None,
            subset_path=None,
            glyph_count=self._glyph_count(request),
            bytes_written=len(data),
            permission=permission,
            optimisation=request.optimisation,
            packaging_metadata=metadata,
        )

    def _subset_with_fonttools(
        self,
        request: FontEmbeddingRequest,
        text_payload: str,
        permission: EmbeddingPermission,
    ) -> FontEmbeddingResult | None:
        if TTFont is None or fonttools_subset is None:  # pragma: no cover - optional dependency guard
            logger.debug("fontTools not available; cannot subset font %s", request.font_path)
            return None

        font = None
        try:
            # Check if font data is already loaded (e.g., from web fonts)
            if "font_data" in request.metadata:
                from io import BytesIO
                font_data = request.metadata["font_data"]
                if not isinstance(font_data, bytes):
                    logger.debug("Invalid font_data type in metadata: %s", type(font_data))
                    return None
                font = TTFont(BytesIO(font_data), lazy=False)
            else:
                # Fall back to reading from filesystem
                font = TTFont(request.font_path, lazy=False)

            subset_bytes = self._perform_subsetting(font, text_payload, request)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("fontTools subsetting failed: %s", exc)
            subset_bytes = None
        finally:
            try:
                if font is not None:
                    font.close()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

        if subset_bytes is None:
            return None

        try:
            payload = self._build_eot_payload(subset_bytes, request)
        except EOTConversionError as exc:
            logger.debug("EOT conversion failed: %s", exc)
            return None

        metadata = {
            "subset_strategy": request.subset_strategy,
            "preserve_hinting": request.preserve_hinting,
            "font_path": request.font_path,
            "glyph_ids": request.glyph_ids,
            "characters": request.characters,
            "subset_bytes": subset_bytes,
            "font_data": payload.eot_bytes,
            "eot_bytes": payload.eot_bytes,
            "font_guid": str(payload.guid) if payload.guid else None,
            "font_root_string": payload.root_string,
            "font_style_kind": payload.style_kind,
            "font_style_flags": dict(payload.style_flags),
            "subset_prefix": payload.subset_prefix,
            "font_charset": payload.charset,
            "font_panose": payload.panose,
            "font_unicode_ranges": payload.unicode_ranges,
            "font_codepage_ranges": payload.codepage_ranges,
            "font_pitch_family": payload.pitch_family,
            "optimisation": request.optimisation.value,
            "permission": permission.value,
        }
        metadata.update(request.metadata)

        return FontEmbeddingResult(
            relationship_id=None,
            subset_path=None,
            glyph_count=self._glyph_count(request),
            bytes_written=len(subset_bytes),
            permission=permission,
            optimisation=request.optimisation,
            packaging_metadata=metadata,
        )

    def _build_eot_payload(
        self,
        subset_bytes: bytes,
        request: FontEmbeddingRequest,
    ) -> EmbeddedFontPayload:
        metadata = request.metadata or {}
        style_kind = _style_kind_from_metadata(metadata)
        style_name = _style_name_from_kind(style_kind)
        guid = uuid.uuid4()
        resolved_family = (
            metadata.get("resolved_family")
            or metadata.get("font_family")
            or Path(request.font_path).stem
            or "EmbeddedFont"
        )
        eot_result = build_eot(
            subset_bytes,
            resolved_family=resolved_family,
            resolved_style=style_name,
            root_string=metadata.get("font_root_string"),
            guid=guid,
        )
        style_flags = _style_flags_from_metadata(metadata, style_kind)
        pitch_family = _derive_pitch_family(eot_result.panose, style_flags)
        return EmbeddedFontPayload(
            subset_bytes=subset_bytes,
            eot_bytes=eot_result.data,
            guid=eot_result.guid,
            root_string=eot_result.root_string,
            style_kind=style_kind,
            style_flags=style_flags,
            subset_prefix=metadata.get("subset_prefix"),
            charset=eot_result.charset,
            panose=eot_result.panose,
            unicode_ranges=eot_result.unicode_ranges,
            codepage_ranges=eot_result.codepage_ranges,
            fs_type=eot_result.fs_type,
            pitch_family=pitch_family,
        )

    def _perform_subsetting(
        self,
        font: "TTFont",
        text: str,
        request: FontEmbeddingRequest,
    ) -> bytes | None:
        options = fonttools_subset.Options()
        options.hinting = request.preserve_hinting
        strategy = (request.subset_strategy or "glyph").lower()
        if strategy == "glyph":
            options.desubroutinize = False
        elif strategy == "character":
            options.desubroutinize = False
        elif strategy == "aggressive":
            options.desubroutinize = True
            options.hinting = False
            options.legacy_kern = False

        optimisation = request.optimisation
        if optimisation == FontOptimisationLevel.NONE:
            options.hinting = request.preserve_hinting
            options.drop_tables = []
        elif optimisation == FontOptimisationLevel.BASIC:
            # Keep essential layout tables but remove bitmap strikes.
            options.drop_tables = ["sbix", "EBLC", "EBDT"]
        elif optimisation == FontOptimisationLevel.AGGRESSIVE:
            options.hinting = False
            options.drop_tables = ["DSIG", "GPOS", "GSUB", "sbix", "EBLC", "EBDT"]

        if not request.preserve_layout_tables:
            tables = set(options.drop_tables or [])
            tables.update({"GPOS", "GSUB", "BASE"})
            options.drop_tables = sorted(tables)

        try:
            subsetter = fonttools_subset.Subsetter(options=options)
            subsetter.populate(text=text)
            subsetter.subset(font)

            with tempfile.NamedTemporaryFile(
                suffix=".ttf",
                delete=False,
                dir=project_temp_dir(),
            ) as temp_file:
                temp_path = Path(temp_file.name)
            try:
                font.save(temp_path)
                data = temp_path.read_bytes()
            finally:
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            return data
        except Exception as exc:  # pragma: no cover - defensive path
            logger.debug("fontTools subset operation failed: %s", exc)
            return None

    def _glyphs_to_text(self, glyph_ids: Iterable[int]) -> str:
        chars: list[str] = []
        for glyph_id in glyph_ids:
            if 0 <= glyph_id <= 0x10FFFF:
                try:
                    chars.append(chr(glyph_id))
                except ValueError:  # pragma: no cover - extremely rare
                    continue
        return "".join(chars)

    def _prepare_subset_text(self, request: FontEmbeddingRequest) -> str:
        if request.characters:
            return "".join(request.characters)
        return self._glyphs_to_text(request.glyph_ids)

    def _glyph_count(self, request: FontEmbeddingRequest) -> int:
        if request.glyph_ids:
            return len(set(request.glyph_ids))
        if request.characters:
            return len(set(request.characters))
        return 0

    def _read_embedding_permission(self, font_path: str) -> EmbeddingPermission:
        if TTFont is None:  # pragma: no cover - optional dependency guard
            return EmbeddingPermission.UNKNOWN
        try:
            font = TTFont(font_path, lazy=True)
        except Exception:
            return EmbeddingPermission.UNKNOWN
        try:
            if "OS/2" not in font:
                return EmbeddingPermission.INSTALLABLE
            os2_table = font["OS/2"]
            fs_type = int(getattr(os2_table, "fsType", 0))
            if fs_type & 0x0002:
                return EmbeddingPermission.RESTRICTED
            if fs_type & 0x0004:
                return EmbeddingPermission.PREVIEW_PRINT
            if fs_type & 0x0008:
                return EmbeddingPermission.EDITABLE
            if fs_type & 0x0100:
                return EmbeddingPermission.NO_SUBSETTING
            if fs_type & 0x0200:
                return EmbeddingPermission.BITMAP_ONLY
            return EmbeddingPermission.INSTALLABLE
        except Exception:  # pragma: no cover - defensive fallback
            return EmbeddingPermission.UNKNOWN
        finally:
            try:
                font.close()
            except Exception:
                pass

    def _cache_key(self, request: FontEmbeddingRequest) -> str:
        digest = sha1()
        digest.update(os.fsencode(request.font_path))
        digest.update(str(request.glyph_ids).encode("utf-8"))
        digest.update("/".join(request.characters).encode("utf-8"))
        digest.update(request.subset_strategy.encode("utf-8"))
        digest.update(b"1" if request.preserve_hinting else b"0")
        digest.update(request.optimisation.value.encode("utf-8"))
        return digest.hexdigest()


def _style_kind_from_metadata(metadata: Mapping[str, object]) -> str:
    value = str(metadata.get("font_style_kind") or "").lower()
    if value == "bolditalic":
        return "boldItalic"
    if value in {"regular", "bold", "italic", "boldItalic"}:
        return "regular" if value == "regular" else value
    bold = bool(metadata.get("bold"))
    italic = bool(metadata.get("italic"))
    if bold and italic:
        return "boldItalic"
    if bold:
        return "bold"
    if italic:
        return "italic"
    return "regular"


def _style_name_from_kind(style_kind: str) -> str:
    mapping = {
        "regular": "Regular",
        "bold": "Bold",
        "italic": "Italic",
        "boldItalic": "Bold Italic",
    }
    return mapping.get(style_kind, "Regular")


def _style_flags_from_metadata(metadata: Mapping[str, object], style_kind: str) -> dict[str, bool]:
    bold = bool(metadata.get("bold"))
    italic = bool(metadata.get("italic"))
    if style_kind == "boldItalic":
        bold = True
        italic = True
    elif style_kind == "bold":
        bold = True
    elif style_kind == "italic":
        italic = True
    return {
        "bold": bold,
        "italic": italic,
        "style_kind": style_kind,
    }


def _derive_pitch_family(panose: bytes, style_flags: Mapping[str, object]) -> int:
    if not panose:
        return 0x32  # variable pitch, swiss
    family_type = panose[0]
    serif_style = panose[1] if len(panose) > 1 else 0

    family_nibble = 0x20  # default to SWISS
    if family_type == 2:  # Latin text
        if serif_style in {11, 12, 13, 14, 15, 16, 17, 18}:  # sans serif styles
            family_nibble = 0x20
        else:
            family_nibble = 0x10  # Roman
    elif family_type == 3:
        family_nibble = 0x40  # Script
    elif family_type == 4:
        family_nibble = 0x50  # Decorative
    elif family_type == 5:
        family_nibble = 0x30  # Symbol/modern

    pitch_bits = 0x2  # Variable pitch
    if style_flags.get("monospace"):
        pitch_bits = 0x1

    return (family_nibble & 0xF0) | (pitch_bits & 0x0F)


__all__ = [
    "EmbeddingPermission",
    "FontOptimisationLevel",
    "FontEmbeddingEngine",
    "FontEmbeddingRequest",
    "FontEmbeddingResult",
]
