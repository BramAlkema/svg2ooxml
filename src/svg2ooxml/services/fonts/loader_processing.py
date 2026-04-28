"""Font payload processing helpers."""

from __future__ import annotations

from .loader_types import LoadedFont
from .svg_font_converter import convert_svg_font


class FontLoaderProcessingMixin:
    """Detect, convert, and finalize loaded font payloads."""

    def _finalize_loaded_font(
        self,
        raw_data: bytes,
        *,
        source_url: str,
        format_hint: str | None = None,
        font_id: str | None = None,
    ) -> LoadedFont | None:
        if len(raw_data) > self.max_size:
            self._logger.warning(
                "Font payload exceeds size limit: %d bytes > %d bytes",
                len(raw_data),
                self.max_size,
            )
            return None

        font_format = self._detect_format(raw_data, format_hint)
        processed = self._process_font_payload(raw_data, font_format, font_id)
        if processed is None:
            return None
        font_data, loaded_format, decompressed = processed
        if len(font_data) > self.max_size:
            self._logger.warning(
                "Processed font payload exceeds size limit: %d bytes > %d bytes",
                len(font_data),
                self.max_size,
            )
            return None

        return LoadedFont(
            data=font_data,
            format=loaded_format,
            source_url=source_url,
            decompressed=decompressed,
        )

    def _process_font_payload(
        self,
        raw_data: bytes,
        font_format: str,
        font_id: str | None,
    ) -> tuple[bytes, str, bool] | None:
        if font_format == "svg":
            converted = self._convert_svg_font(raw_data, font_id)
            if converted is None:
                return None
            return converted, "ttf", True
        if font_format == "woff2":
            decompressed_data = self._decompress_woff2(raw_data)
            if decompressed_data is None:
                return None
            return decompressed_data, "ttf", True
        if font_format == "woff":
            decompressed_data = self._decompress_woff(raw_data)
            if decompressed_data is None:
                return None
            return decompressed_data, "ttf", True
        return raw_data, font_format, False

    def _detect_format(self, data: bytes, hint: str | None = None) -> str:
        """Detect font format from magic bytes or hint."""
        if len(data) >= 4:
            magic = data[:4]
            if magic == b"wOFF":
                return "woff"
            if magic == b"wOF2":
                return "woff2"
            if magic in (b"\x00\x01\x00\x00", b"true", b"typ1"):
                return "ttf"
            if magic == b"OTTO":
                return "otf"

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
        return "ttf"

    def _convert_svg_font(self, data: bytes, font_id: str | None) -> bytes | None:
        if not self.allow_svg_fonts:
            self._logger.warning("SVG font conversion disabled by policy.")
            return None
        converted = convert_svg_font(data, font_id=font_id)
        if converted is None:
            self._logger.warning("SVG font conversion failed.")
        return converted


__all__ = ["FontLoaderProcessingMixin"]
