"""Font loading and decompression for web fonts."""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict
from urllib.parse import urldefrag

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.ir.fonts import FontFaceSrc
    from svg2ooxml.services.fonts.fetcher import FontFetcher

from svg2ooxml.services.fonts.fontforge_utils import (
    FONTFORGE_AVAILABLE,
    generate_font_bytes,
    open_font,
)
from svg2ooxml.services.fonts.svg_font_converter import convert_svg_font

logger = logging.getLogger(__name__)

MAX_FONT_SIZE = 10 * 1024 * 1024  # 10 MiB safety limit
DATA_URI_PATTERN = re.compile(
    r"^data:(?P<mime>[^;,]+)?(?:;(?P<encoding>base64))?,(?P<data>.*)$",
    re.IGNORECASE
)


class WOFFTableEntry(TypedDict):
    """WOFF table directory entry."""
    tag: bytes
    comp_offset: int
    comp_length: int
    orig_length: int
    checksum: bytes


@dataclass
class LoadedFont:
    """Result of loading a font from a source.

    Attributes:
        data: Raw font file bytes (TTF/OTF format after decompression)
        format: Font format ('ttf', 'otf', 'woff', 'woff2')
        source_url: Original URL/data URI
        decompressed: Whether font was decompressed (WOFF/WOFF2)
        size_bytes: Size of loaded data
    """
    data: bytes
    format: str
    source_url: str
    decompressed: bool = False
    size_bytes: int = 0

    def __post_init__(self) -> None:
        if self.size_bytes == 0:
            self.size_bytes = len(self.data)


class FontLoader:
    """Load and decompress fonts from various sources.

    Supports:
    - Data URIs (base64-encoded fonts)
    - Remote HTTP(S) URLs (via FontFetcher)
    - WOFF decompression (zlib)
    - WOFF2 decompression (FontForge)
    """

    def __init__(
        self,
        fetcher: FontFetcher | None = None,
        *,
        allow_network: bool = True,
        max_size: int = MAX_FONT_SIZE,
        base_dir: Path | None = None,
        allow_svg_fonts: bool = True,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize font loader.

        Args:
            fetcher: Optional FontFetcher for remote downloads
            allow_network: Whether to allow network requests
            max_size: Maximum font size in bytes
            logger: Optional logger instance
        """
        self.fetcher = fetcher
        self.allow_network = allow_network
        self.max_size = max_size
        self.base_dir = base_dir
        self.allow_svg_fonts = allow_svg_fonts
        self._logger = logger or globals()["logger"]

    def load_from_src(self, src: FontFaceSrc) -> LoadedFont | None:
        """Load font from a FontFaceSrc.

        Args:
            src: Font source descriptor from @font-face rule

        Returns:
            LoadedFont if successful, None if loading failed
        """
        if src.is_data_uri:
            return self.load_data_uri(src.url, format_hint=src.format)
        elif src.is_remote and self.allow_network:
            return self.load_remote(src.url, src.format)
        elif src.is_local:
            if src.url.startswith("local("):
                self._logger.debug("Skipping local() font reference: %s", src.url)
                return None
            url_no_frag, fragment = urldefrag(src.url)
            resolved = self._resolve_local_path(url_no_frag)
            if resolved is None:
                self._logger.debug("Skipping unresolved local font reference: %s", src.url)
                return None
            return self.load_file(resolved, format_hint=src.format, font_id=fragment)
        else:
            # Relative URL or unsupported
            self._logger.debug("Unsupported font source: %s", src.url)
            return None

    def load_data_uri(self, data_uri: str, *, format_hint: str | None = None) -> LoadedFont | None:
        """Load font from base64 data URI.

        Args:
            data_uri: Data URI string (e.g., "data:font/woff2;base64,...")

        Returns:
            LoadedFont if successful, None if parsing failed
        """
        data_uri, fragment = urldefrag(data_uri)
        match = DATA_URI_PATTERN.match(data_uri)
        if not match:
            self._logger.warning("Invalid data URI format")
            return None

        mime_type = match.group("mime") or "application/octet-stream"
        encoding = match.group("encoding")
        data_str = match.group("data")

        # Decode base64
        if encoding and encoding.lower() == "base64":
            try:
                raw_data = base64.b64decode(data_str)
            except Exception as exc:
                self._logger.warning("Failed to decode base64 data URI: %s", exc)
                return None
        else:
            # URL-encoded or plain text (rare for fonts)
            try:
                raw_data = data_str.encode("utf-8")
            except Exception as exc:
                self._logger.warning("Failed to encode data URI: %s", exc)
                return None

        # Check size limit
        if len(raw_data) > self.max_size:
            self._logger.warning(
                "Data URI font exceeds size limit: %d bytes > %d bytes",
                len(raw_data),
                self.max_size
            )
            return None

        # Detect format from MIME type or magic bytes
        font_format = self._detect_format(raw_data, format_hint or mime_type)

        # Decompress if needed
        decompressed = False
        if font_format == "svg":
            raw_data = self._convert_svg_font(raw_data, fragment)
            if raw_data is None:
                return None
            decompressed = True
            font_format = "ttf"
        elif font_format == "woff2":
            decompressed_data = self._decompress_woff2(raw_data)
            if decompressed_data is None:
                return None
            raw_data = decompressed_data
            decompressed = True
            font_format = "ttf"  # WOFF2 decompresses to TTF
        elif font_format == "woff":
            decompressed_data = self._decompress_woff(raw_data)
            if decompressed_data is None:
                return None
            raw_data = decompressed_data
            decompressed = True
            font_format = "ttf"  # WOFF decompresses to TTF

        return LoadedFont(
            data=raw_data,
            format=font_format,
            source_url=data_uri[:100] + "..." if len(data_uri) > 100 else data_uri,
            decompressed=decompressed,
        )

    def load_remote(self, url: str, format_hint: str | None = None) -> LoadedFont | None:
        """Load font from remote HTTP(S) URL.

        Args:
            url: Remote font URL
            format_hint: Optional format hint from @font-face src

        Returns:
            LoadedFont if successful, None if download failed
        """
        if not self.allow_network:
            self._logger.debug("Network requests disabled, skipping remote font: %s", url)
            return None

        if self.fetcher is None:
            self._logger.warning("No FontFetcher available for remote font: %s", url)
            return None

        url_no_frag, fragment = urldefrag(url)
        # Use fetcher to download
        from .fetcher import FontSource
        source = FontSource(url=url_no_frag, font_family="unknown")

        try:
            path = self.fetcher.fetch(source)
            if path is None:
                self._logger.warning("Failed to fetch remote font: %s", url)
                return None

            # Read downloaded file
            raw_data = path.read_bytes()

            # Detect format
            font_format = format_hint or self._detect_format(raw_data)

            # Decompress if needed
            decompressed = False
            if font_format == "svg":
                raw_data = self._convert_svg_font(raw_data, fragment)
                if raw_data is None:
                    return None
                decompressed = True
                font_format = "ttf"
            elif font_format == "woff2":
                decompressed_data = self._decompress_woff2(raw_data)
                if decompressed_data is None:
                    return None
                raw_data = decompressed_data
                decompressed = True
                font_format = "ttf"
            elif font_format == "woff":
                decompressed_data = self._decompress_woff(raw_data)
                if decompressed_data is None:
                    return None
                raw_data = decompressed_data
                decompressed = True
                font_format = "ttf"

            return LoadedFont(
                data=raw_data,
                format=font_format,
                source_url=url,
                decompressed=decompressed,
            )
        except Exception as exc:
            self._logger.warning("Error loading remote font %s: %s", url, exc)
            return None

    def load_file(
        self,
        path: Path,
        *,
        format_hint: str | None = None,
        font_id: str | None = None,
    ) -> LoadedFont | None:
        """Load font from local file path.

        Args:
            path: Path to font file

        Returns:
            LoadedFont if successful, None if loading failed
        """
        try:
            if not path.exists():
                self._logger.warning("Font file not found: %s", path)
                return None

            raw_data = path.read_bytes()

            if len(raw_data) > self.max_size:
                self._logger.warning("Font file exceeds size limit: %s", path)
                return None

            font_format = self._detect_format(raw_data, format_hint or path.suffix.lstrip("."))

            # Decompress if needed
            decompressed = False
            if font_format == "svg":
                raw_data = self._convert_svg_font(raw_data, font_id)
                if raw_data is None:
                    return None
                decompressed = True
                font_format = "ttf"
            elif font_format == "woff2":
                decompressed_data = self._decompress_woff2(raw_data)
                if decompressed_data is None:
                    return None
                raw_data = decompressed_data
                decompressed = True
                font_format = "ttf"
            elif font_format == "woff":
                decompressed_data = self._decompress_woff(raw_data)
                if decompressed_data is None:
                    return None
                raw_data = decompressed_data
                decompressed = True
                font_format = "ttf"

            return LoadedFont(
                data=raw_data,
                format=font_format,
                source_url=str(path),
                decompressed=decompressed,
            )
        except Exception as exc:
            self._logger.warning("Error loading font file %s: %s", path, exc)
            return None

    # ------------------------------------------------------------------
    # Format detection
    # ------------------------------------------------------------------

    def _detect_format(
        self,
        data: bytes,
        hint: str | None = None
    ) -> str:
        """Detect font format from magic bytes or hint.

        Args:
            data: Font file bytes
            hint: Optional MIME type or extension hint

        Returns:
            Format string: 'ttf', 'otf', 'woff', 'woff2'
        """
        # Check magic bytes first (most reliable)
        if len(data) >= 4:
            magic = data[:4]

            # WOFF: "wOFF"
            if magic == b"wOFF":
                return "woff"

            # WOFF2: "wOF2"
            if magic == b"wOF2":
                return "woff2"

            # TTF: 0x00010000 or "true" or "typ1"
            if magic in (b"\x00\x01\x00\x00", b"true", b"typ1"):
                return "ttf"

            # OTF: "OTTO"
            if magic == b"OTTO":
                return "otf"

        # Fall back to hint
        if hint:
            hint_lower = hint.lower()
            if "svg" in hint_lower:
                return "svg"
            if "woff2" in hint_lower:
                return "woff2"
            if "woff" in hint_lower:
                return "woff"
            if "truetype" in hint_lower or "ttf" in hint_lower:
                return "ttf"
            if "opentype" in hint_lower or "otf" in hint_lower:
                return "otf"

        snippet = data[:256].lstrip().lower()
        if snippet.startswith(b"<?xml") or snippet.startswith(b"<svg"):
            return "svg"

        # Default to TTF
        return "ttf"

    # ------------------------------------------------------------------
    # Decompression
    # ------------------------------------------------------------------

    def _decompress_woff2(self, data: bytes) -> bytes | None:
        """Decompress WOFF2 font to TTF/OTF using FontForge.

        FontForge handles the WOFF2 decode pipeline when built with brotli.

        Args:
            data: WOFF2 compressed bytes

        Returns:
            Decompressed TTF/OTF bytes, or None if decompression failed
        """
        if not FONTFORGE_AVAILABLE:
            self._logger.warning(
                "FontForge not available, cannot decompress WOFF2."
            )
            return None

        try:
            if len(data) < 48:  # Minimum WOFF2 header size
                self._logger.warning("WOFF2 data too short")
                return None

            # Verify WOFF2 signature
            if data[:4] != b"wOF2":
                self._logger.warning("Invalid WOFF2 signature")
                return None
            try:
                reported_length = int.from_bytes(data[8:12], "big")
                num_tables = int.from_bytes(data[12:14], "big")
                total_sfnt_size = int.from_bytes(data[16:20], "big")
                total_compressed_size = int.from_bytes(data[20:24], "big")
            except Exception:
                self._logger.warning("Invalid WOFF2 header fields")
                return None

            if reported_length and reported_length != len(data):
                self._logger.warning("WOFF2 length mismatch")
                return None
            if num_tables == 0 or total_sfnt_size == 0 or total_compressed_size == 0:
                self._logger.warning("WOFF2 header indicates empty payload")
                return None
            if total_compressed_size > len(data) - 48:
                self._logger.warning("WOFF2 compressed payload size is invalid")
                return None

            with open_font(data, suffix=".woff2") as font:
                result = generate_font_bytes(font, suffix=".ttf")

            self._logger.debug(
                "Decompressed WOFF2: %d → %d bytes",
                len(data),
                len(result)
            )

            # Check size limit on decompressed data
            if len(result) > self.max_size:
                self._logger.warning(
                    "Decompressed WOFF2 exceeds size limit: %d > %d",
                    len(result),
                    self.max_size
                )
                return None

            return result

        except Exception as exc:
            self._logger.warning("WOFF2 decompression failed: %s", exc)
            return None

    def _decompress_woff(self, data: bytes) -> bytes | None:
        """Decompress WOFF font to TTF/OTF.

        WOFF uses zlib/gzip compression on individual font tables.

        Args:
            data: WOFF compressed bytes

        Returns:
            Decompressed TTF/OTF bytes, or None if decompression failed
        """
        try:
            # WOFF structure:
            # Header (44 bytes):
            #   - signature: "wOFF" (4 bytes)
            #   - flavor: 0x00010000 for TrueType, OTTO for CFF (4 bytes)
            #   - length: total WOFF file size (4 bytes)
            #   - numTables: number of font tables (2 bytes)
            #   - reserved: 0 (2 bytes)
            #   - totalSfntSize: uncompressed size (4 bytes)
            #   - majorVersion, minorVersion (2 + 2 bytes)
            #   - metaOffset, metaLength, metaOrigLength (4 + 4 + 4 bytes)
            #   - privOffset, privLength (4 + 4 bytes)

            if len(data) < 44:
                self._logger.warning("WOFF data too short")
                return None

            # Parse header
            signature = data[0:4]
            if signature != b"wOFF":
                self._logger.warning("Invalid WOFF signature")
                return None

            flavor = data[4:8]
            num_tables = int.from_bytes(data[12:14], "big")
            total_sfnt_size = int.from_bytes(data[16:20], "big")

            if total_sfnt_size > self.max_size:
                self._logger.warning("Decompressed WOFF exceeds size limit")
                return None

            # Build output buffer
            output = BytesIO()

            # Write sfnt header (12 bytes for TTF/OTF)
            output.write(flavor)  # sfntVersion
            output.write(num_tables.to_bytes(2, "big"))  # numTables

            # Calculate searchRange, entrySelector, rangeShift
            entry_selector = 0
            search_range = 1
            while search_range <= num_tables:
                search_range *= 2
                entry_selector += 1
            entry_selector -= 1
            search_range = (2 ** entry_selector) * 16
            range_shift = num_tables * 16 - search_range

            output.write(search_range.to_bytes(2, "big"))
            output.write(entry_selector.to_bytes(2, "big"))
            output.write(range_shift.to_bytes(2, "big"))

            # Parse table directory
            table_entries: list[WOFFTableEntry] = []
            offset = 44  # After WOFF header

            for _ in range(num_tables):
                if offset + 20 > len(data):
                    self._logger.warning("WOFF table directory truncated")
                    return None

                tag = data[offset:offset+4]
                comp_offset = int.from_bytes(data[offset+4:offset+8], "big")
                comp_length = int.from_bytes(data[offset+8:offset+12], "big")
                orig_length = int.from_bytes(data[offset+12:offset+16], "big")
                orig_checksum = data[offset+16:offset+20]

                entry: WOFFTableEntry = {
                    "tag": tag,
                    "comp_offset": comp_offset,
                    "comp_length": comp_length,
                    "orig_length": orig_length,
                    "checksum": orig_checksum,
                }
                table_entries.append(entry)
                offset += 20

            # Write table directory
            current_offset = 12 + num_tables * 16
            for entry in table_entries:
                output.write(entry["tag"])
                output.write(entry["checksum"])
                output.write(current_offset.to_bytes(4, "big"))
                output.write(entry["orig_length"].to_bytes(4, "big"))
                current_offset += entry["orig_length"]
                # Align to 4-byte boundary
                if current_offset % 4 != 0:
                    current_offset += 4 - (current_offset % 4)

            # Decompress and write table data
            for entry in table_entries:
                comp_offset = entry["comp_offset"]
                comp_length = entry["comp_length"]
                orig_length = entry["orig_length"]

                if comp_offset + comp_length > len(data):
                    self._logger.warning("WOFF table data out of bounds")
                    return None

                compressed_data = data[comp_offset:comp_offset + comp_length]

                # Decompress if compressed
                if comp_length < orig_length:
                    try:
                        # WOFF uses zlib compression (with header), not raw deflate
                        import zlib
                        table_data = zlib.decompress(compressed_data)
                    except Exception as exc:
                        self._logger.warning("Failed to decompress WOFF table: %s", exc)
                        return None
                else:
                    # Not compressed
                    table_data = compressed_data

                if len(table_data) != orig_length:
                    self._logger.warning("WOFF table size mismatch")
                    return None

                output.write(table_data)

                # Pad to 4-byte boundary
                padding = (4 - (len(table_data) % 4)) % 4
                if padding:
                    output.write(b"\x00" * padding)

            result = output.getvalue()
            self._logger.debug("Decompressed WOFF: %d → %d bytes", len(data), len(result))
            return result

        except Exception as exc:
            self._logger.warning("WOFF decompression failed: %s", exc)
            return None

    def _convert_svg_font(self, data: bytes, font_id: str | None) -> bytes | None:
        if not self.allow_svg_fonts:
            self._logger.warning("SVG font conversion disabled by policy.")
            return None
        converted = convert_svg_font(data, font_id=font_id)
        if converted is None:
            self._logger.warning("SVG font conversion failed.")
        return converted

    def _resolve_local_path(self, url: str) -> Path | None:
        if not url:
            return None
        path = Path(url)
        if path.is_absolute():
            if path.exists():
                return path
            if self.base_dir is None:
                return path
            try:
                relative = path.relative_to(path.anchor)
            except ValueError:
                relative = Path(*path.parts[1:])
            for base in (self.base_dir, self.base_dir.parent):
                candidate = (base / relative).resolve()
                if candidate.exists():
                    return candidate
            return path
        if self.base_dir is None:
            return None
        return (self.base_dir / path).resolve()


__all__ = [
    "FontLoader",
    "LoadedFont",
    "MAX_FONT_SIZE",
    "FONTFORGE_AVAILABLE",
]
