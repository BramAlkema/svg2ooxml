"""Font embedding engine with basic subsetting support."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from hashlib import sha1
from pathlib import Path

from svg2ooxml.services.fonts.eot import EOTConversionError, build_eot
from svg2ooxml.services.fonts.fontforge_utils import (
    FONTFORGE_AVAILABLE,
    generate_font_bytes,
    get_table_data,
    open_font,
)
from svg2ooxml.services.fonts.opentype_utils import parse_os2_table

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
    """Subset fonts using FontForge when available and track simple stats."""

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

        font_data = None
        if isinstance(request.metadata, Mapping):
            data = request.metadata.get("font_data")
            if isinstance(data, (bytes, bytearray)):
                font_data = bytes(data)
        permission = self._read_embedding_permission(request.font_path, font_data)
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

        effective_request = request
        if strategy != "none" and not FONTFORGE_AVAILABLE:
            logger.debug("FontForge not available; falling back to direct embedding for %s", request.font_path)
            strategy = "none"
            effective_request = replace(request, subset_strategy="none")

        if strategy == "none":
            result = self._subset_copy(effective_request, permission)
        else:
            result = self._subset_with_fontforge(effective_request, text_payload, permission)

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

    def _subset_with_fontforge(
        self,
        request: FontEmbeddingRequest,
        text_payload: str,
        permission: EmbeddingPermission,
    ) -> FontEmbeddingResult | None:
        if not FONTFORGE_AVAILABLE:  # pragma: no cover - optional dependency guard
            logger.debug("FontForge not available; cannot subset font %s", request.font_path)
            return None

        subset_bytes = None
        try:
            # Check if font data is already loaded (e.g., from web fonts)
            if "font_data" in request.metadata:
                font_data = request.metadata["font_data"]
                if not isinstance(font_data, bytes):
                    logger.debug("Invalid font_data type in metadata: %s", type(font_data))
                    return None
                with open_font(font_data, suffix=".ttf") as font:
                    subset_bytes = self._perform_subsetting(font, text_payload)
            else:
                font_suffix = Path(request.font_path).suffix or ".ttf"
                with open_font(request.font_path, suffix=font_suffix) as font:
                    subset_bytes = self._perform_subsetting(font, text_payload)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("FontForge subsetting failed: %s", exc)
            subset_bytes = None

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
        font: object,
        text: str,
    ) -> bytes | None:
        try:
            selection = getattr(font, "selection", None)
            if selection is None:
                return None

            selection.none()
            selected_any = False
            text_lookup = text or ""
            text_set = set(text_lookup)
            for ch in sorted(set(text)):
                codepoint = ord(ch)
                try:
                    if selected_any:
                        selection.select(("more", "unicode"), codepoint)
                    else:
                        selection.select(("unicode",), codepoint)
                        selected_any = True
                except Exception:
                    continue

            selected_any = self._select_glyphs_by_sequences(
                font,
                selection,
                text_lookup,
                text_set,
                selected_any,
            )

            selected_any = self._select_ligature_glyphs(
                font,
                selection,
                text_lookup,
                selected_any,
            )

            for glyph_name in (".notdef", ".null", "nonmarkingreturn"):
                try:
                    if selected_any:
                        selection.select(("more", "glyphs"), glyph_name)
                    else:
                        selection.select(("glyphs",), glyph_name)
                        selected_any = True
                except Exception:
                    continue

            if not selected_any:
                return None

            try:
                selection.invert()
                font.clear()
            except Exception as exc:
                logger.debug("FontForge glyph pruning failed: %s", exc)

            return generate_font_bytes(font, suffix=".ttf")
        except Exception as exc:  # pragma: no cover - defensive path
            logger.debug("FontForge subset operation failed: %s", exc)
            return None

    def _select_glyphs_by_sequences(
        self,
        font: object,
        selection: object,
        text_lookup: str,
        text_set: set[str],
        selected_any: bool,
    ) -> bool:
        """Select glyphs that map to multi-character or alternate unicode sequences."""
        glyphs_iter = getattr(font, "glyphs", None)
        if glyphs_iter is None:
            return selected_any
        try:
            glyphs = glyphs_iter()
        except Exception:
            return selected_any

        for glyph in glyphs:
            sequences = self._glyph_unicode_sequences(glyph)
            if not sequences:
                continue
            for seq in sequences:
                if not seq:
                    continue
                if len(seq) == 1:
                    if seq not in text_set:
                        continue
                else:
                    if seq not in text_lookup:
                        continue
                try:
                    if selected_any:
                        selection.select(("more", "glyphs"), glyph.glyphname)
                    else:
                        selection.select(("glyphs",), glyph.glyphname)
                        selected_any = True
                    break
                except Exception:
                    continue
        return selected_any

    def _select_ligature_glyphs(
        self,
        font: object,
        selection: object,
        text_lookup: str,
        selected_any: bool,
    ) -> bool:
        """Select ligature glyphs whose component sequences appear in the text."""
        if not text_lookup:
            return selected_any
        glyphs_iter = getattr(font, "glyphs", None)
        if glyphs_iter is None:
            return selected_any
        try:
            glyphs = glyphs_iter()
        except Exception:
            return selected_any

        for glyph in glyphs:
            sequences = self._glyph_ligature_sequences(font, glyph)
            if not sequences:
                continue
            for seq in sequences:
                if not seq or seq not in text_lookup:
                    continue
                try:
                    if selected_any:
                        selection.select(("more", "glyphs"), glyph.glyphname)
                    else:
                        selection.select(("glyphs",), glyph.glyphname)
                        selected_any = True
                    break
                except Exception:
                    continue
        return selected_any

    @staticmethod
    def _glyph_unicode_sequences(glyph: object) -> list[str]:
        sequences: list[str] = []

        def add_sequence(value: object) -> None:
            seq = FontEmbeddingEngine._coerce_unicode_sequence(value)
            if seq:
                sequences.append(seq)

        add_sequence(getattr(glyph, "unicode", None))
        altuni = getattr(glyph, "altuni", None)
        if altuni:
            for entry in altuni:
                if isinstance(entry, (tuple, list)) and entry:
                    add_sequence(entry[0])
                else:
                    add_sequence(entry)
        return sequences

    @staticmethod
    def _coerce_unicode_sequence(value: object) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, int):
            if 0 <= value <= 0x10FFFF:
                try:
                    return chr(value)
                except ValueError:  # pragma: no cover - invalid codepoint
                    return None
            return None
        if isinstance(value, (tuple, list)):
            chars: list[str] = []
            for item in value:
                if isinstance(item, int):
                    if 0 <= item <= 0x10FFFF:
                        try:
                            chars.append(chr(item))
                        except ValueError:
                            continue
                elif isinstance(item, str) and item:
                    chars.append(item)
            return "".join(chars) if chars else None
        return None

    def _glyph_ligature_sequences(self, font: object, glyph: object) -> list[str]:
        sequences: list[str] = []
        get_pos_sub = getattr(glyph, "getPosSub", None)
        if get_pos_sub is None:
            return sequences
        try:
            entries = get_pos_sub("*")
        except Exception:
            return sequences
        if not entries:
            return sequences
        for entry in entries:
            if not entry or len(entry) < 3:
                continue
            kind = str(entry[1]).lower()
            if "ligature" not in kind:
                continue
            component_names = entry[2:]
            chars: list[str] = []
            for name in component_names:
                char = self._glyph_name_to_char(font, name)
                if char is None:
                    chars = []
                    break
                chars.append(char)
            if chars:
                sequences.append("".join(chars))
        return sequences

    def _glyph_name_to_char(self, font: object, name: object) -> str | None:
        if not isinstance(name, str):
            return None
        try:
            glyph = font[name]
        except Exception:
            return None
        sequences = self._glyph_unicode_sequences(glyph)
        for seq in sequences:
            if seq:
                return seq[0]
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

    def _read_embedding_permission(
        self,
        font_path: str,
        font_data: bytes | None = None,
    ) -> EmbeddingPermission:
        if not FONTFORGE_AVAILABLE:  # pragma: no cover - optional dependency guard
            return EmbeddingPermission.UNKNOWN
        try:
            if font_data is not None:
                with open_font(font_data, suffix=".ttf") as font:
                    os2_table = get_table_data(font, "OS/2")
            else:
                font_suffix = Path(font_path).suffix or ".ttf"
                with open_font(font_path, suffix=font_suffix) as font:
                    os2_table = get_table_data(font, "OS/2")
        except Exception:
            return EmbeddingPermission.UNKNOWN
        try:
            os2 = parse_os2_table(os2_table)
            fs_type = int(os2.fs_type or 0)
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
