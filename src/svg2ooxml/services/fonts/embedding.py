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

from svg2ooxml.common.tempfiles import project_temp_dir

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

        metadata = {
            "subset_strategy": request.subset_strategy,
            "preserve_hinting": request.preserve_hinting,
            "font_path": request.font_path,
            "glyph_ids": request.glyph_ids,
            "characters": request.characters,
            "font_data": subset_bytes,
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


__all__ = [
    "EmbeddingPermission",
    "FontOptimisationLevel",
    "FontEmbeddingEngine",
    "FontEmbeddingRequest",
    "FontEmbeddingResult",
]
