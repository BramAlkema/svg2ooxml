"""Unit tests for FontLoader."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

from svg2ooxml.ir.fonts import FontFaceSrc
from svg2ooxml.services.fonts.loader import (
    FONTFORGE_AVAILABLE,
    FontLoader,
    LoadedFont,
)


class TestFontLoader:
    """Tests for FontLoader."""

    def test_load_data_uri_base64_ttf(self):
        """Load TTF font from base64 data URI."""
        # Create minimal TTF header (magic: 0x00010000)
        ttf_data = b"\x00\x01\x00\x00" + b"\x00" * 100
        b64_data = base64.b64encode(ttf_data).decode("ascii")
        data_uri = f"data:font/ttf;base64,{b64_data}"

        loader = FontLoader()
        result = loader.load_data_uri(data_uri)

        assert result is not None
        assert result.format == "ttf"
        assert result.data == ttf_data
        assert result.decompressed is False
        assert result.size_bytes == len(ttf_data)
        assert "data:font/ttf" in result.source_url

    def test_load_data_uri_base64_otf(self):
        """Load OTF font from base64 data URI."""
        # Create minimal OTF header (magic: "OTTO")
        otf_data = b"OTTO" + b"\x00" * 100
        b64_data = base64.b64encode(otf_data).decode("ascii")
        data_uri = f"data:font/otf;base64,{b64_data}"

        loader = FontLoader()
        result = loader.load_data_uri(data_uri)

        assert result is not None
        assert result.format == "otf"
        assert result.data == otf_data

    def test_load_data_uri_woff_header(self):
        """Detect WOFF format from data URI (decompression tested separately)."""
        # Create minimal WOFF header (without full decompression)
        woff_data = b"wOFF" + b"\x00" * 100
        b64_data = base64.b64encode(woff_data).decode("ascii")
        _data_uri = f"data:font/woff;base64,{b64_data}"

        loader = FontLoader()
        # This will fail decompression but should detect format
        # Just testing format detection here
        assert loader._detect_format(woff_data) == "woff"

    def test_load_data_uri_invalid_base64(self):
        """Invalid base64 returns None."""
        data_uri = "data:font/ttf;base64,NOT_VALID_BASE64!!!"

        loader = FontLoader()
        result = loader.load_data_uri(data_uri)

        assert result is None

    def test_load_data_uri_no_base64_encoding(self):
        """Data URI without base64 encoding (rare)."""
        data_uri = "data:font/ttf,plaintext"

        loader = FontLoader()
        result = loader.load_data_uri(data_uri)

        # Should succeed but with plain text data
        assert result is not None

    def test_load_data_uri_exceeds_size_limit(self):
        """Data URI exceeding size limit returns None."""
        # Create data larger than limit
        large_data = b"\x00\x01\x00\x00" + b"X" * (11 * 1024 * 1024)  # 11 MB
        b64_data = base64.b64encode(large_data).decode("ascii")
        data_uri = f"data:font/ttf;base64,{b64_data}"

        loader = FontLoader(max_size=10 * 1024 * 1024)  # 10 MB limit
        result = loader.load_data_uri(data_uri)

        assert result is None

    def test_load_data_uri_invalid_format(self):
        """Invalid data URI format returns None."""
        loader = FontLoader()

        # Missing data: prefix
        result = loader.load_data_uri("font/ttf;base64,...")
        assert result is None

        # Empty string
        result = loader.load_data_uri("")
        assert result is None

    def test_load_from_src_data_uri(self):
        """Load font from FontFaceSrc with data URI."""
        ttf_data = b"\x00\x01\x00\x00" + b"\x00" * 50
        b64_data = base64.b64encode(ttf_data).decode("ascii")
        data_uri = f"data:font/ttf;base64,{b64_data}"

        src = FontFaceSrc(url=data_uri, format="ttf")
        loader = FontLoader()
        result = loader.load_from_src(src)

        assert result is not None
        assert result.format == "ttf"
        assert result.data == ttf_data

    def test_load_from_src_local_font(self):
        """Loading local() font returns None."""
        src = FontFaceSrc(url="local(Arial)", format=None)
        loader = FontLoader()
        result = loader.load_from_src(src)

        assert result is None

    def test_load_from_src_remote_no_network(self):
        """Remote font with network disabled returns None."""
        src = FontFaceSrc(url="https://example.com/font.woff2", format="woff2")
        loader = FontLoader(allow_network=False)
        result = loader.load_from_src(src)

        assert result is None

    def test_load_from_src_remote_no_fetcher(self):
        """Remote font without fetcher returns None."""
        src = FontFaceSrc(url="https://example.com/font.woff2", format="woff2")
        loader = FontLoader(fetcher=None, allow_network=True)
        result = loader.load_from_src(src)

        assert result is None

    def test_resolve_local_path_absolute_fallback(self, tmp_path: Path):
        """Absolute paths fall back to base_dir parent when missing."""
        base_dir = tmp_path / "svg"
        base_dir.mkdir(parents=True)
        resources_dir = tmp_path / "resources"
        resources_dir.mkdir(parents=True)
        resource_file = resources_dir / "Blocky.svg"
        resource_file.write_text("<svg/>", encoding="utf-8")

        loader = FontLoader(base_dir=base_dir)
        absolute = Path("/") / "resources" / "Blocky.svg"
        resolved = loader._resolve_local_path(str(absolute))

        assert resolved == resource_file.resolve()

    def test_load_file_ttf(self, tmp_path: Path):
        """Load TTF font from file."""
        ttf_data = b"\x00\x01\x00\x00" + b"\x00" * 100
        font_file = tmp_path / "test.ttf"
        font_file.write_bytes(ttf_data)

        loader = FontLoader()
        result = loader.load_file(font_file)

        assert result is not None
        assert result.format == "ttf"
        assert result.data == ttf_data
        assert result.source_url == str(font_file)

    def test_load_file_woff_detection(self, tmp_path: Path):
        """Detect WOFF font from file (decompression tested separately)."""
        woff_data = b"wOFF" + b"\x00" * 100
        font_file = tmp_path / "test.woff"
        font_file.write_bytes(woff_data)

        loader = FontLoader()
        # Will fail decompression, just test detection
        assert loader._detect_format(woff_data, ".woff") == "woff"

    def test_load_file_not_found(self, tmp_path: Path):
        """Loading non-existent file returns None."""
        loader = FontLoader()
        result = loader.load_file(tmp_path / "notfound.ttf")

        assert result is None

    def test_load_file_exceeds_size_limit(self, tmp_path: Path):
        """File exceeding size limit returns None."""
        large_data = b"\x00\x01\x00\x00" + b"X" * (11 * 1024 * 1024)
        font_file = tmp_path / "large.ttf"
        font_file.write_bytes(large_data)

        loader = FontLoader(max_size=10 * 1024 * 1024)
        result = loader.load_file(font_file)

        assert result is None

    def test_detect_format_ttf_magic(self):
        """Detect TTF from magic bytes."""
        loader = FontLoader()

        # TTF magic: 0x00010000
        assert loader._detect_format(b"\x00\x01\x00\x00" + b"\x00" * 10) == "ttf"

        # TTF magic: "true"
        assert loader._detect_format(b"true" + b"\x00" * 10) == "ttf"

    def test_detect_format_otf_magic(self):
        """Detect OTF from magic bytes."""
        loader = FontLoader()

        # OTF magic: "OTTO"
        assert loader._detect_format(b"OTTO" + b"\x00" * 10) == "otf"

    def test_detect_format_woff_magic(self):
        """Detect WOFF from magic bytes."""
        loader = FontLoader()

        # WOFF magic: "wOFF"
        assert loader._detect_format(b"wOFF" + b"\x00" * 10) == "woff"

    def test_detect_format_woff2_magic(self):
        """Detect WOFF2 from magic bytes."""
        loader = FontLoader()

        # WOFF2 magic: "wOF2"
        assert loader._detect_format(b"wOF2" + b"\x00" * 10) == "woff2"

    def test_detect_format_from_hint(self):
        """Detect format from MIME type hint."""
        loader = FontLoader()

        # No magic bytes, use hint
        assert loader._detect_format(b"\x00" * 10, "font/woff2") == "woff2"
        assert loader._detect_format(b"\x00" * 10, "font/woff") == "woff"
        assert loader._detect_format(b"\x00" * 10, "font/ttf") == "ttf"
        assert loader._detect_format(b"\x00" * 10, "truetype") == "ttf"
        assert loader._detect_format(b"\x00" * 10, "font/otf") == "otf"
        assert loader._detect_format(b"\x00" * 10, "opentype") == "otf"

    def test_detect_format_default_ttf(self):
        """Default to TTF when format unknown."""
        loader = FontLoader()

        # Unknown magic, no hint
        assert loader._detect_format(b"UNKN" + b"\x00" * 10) == "ttf"

    def test_decompress_woff_realistic(self):
        """WOFF decompression with realistic structure (complex, marked as TODO)."""
        # Creating a fully valid WOFF is complex - requires proper table structure
        # For now, just test that invalid WOFF returns None
        # TODO: Add full WOFF round-trip test with real font file
        loader = FontLoader()

        # Invalid WOFF should return None
        invalid_woff = b"wOFF" + b"\x00" * 100
        result = loader._decompress_woff(invalid_woff)
        assert result is None  # Expected to fail with minimal data

    def test_decompress_woff_invalid_signature(self):
        """Invalid WOFF signature returns None."""
        loader = FontLoader()

        # Wrong signature
        result = loader._decompress_woff(b"INVD" + b"\x00" * 100)
        assert result is None

    def test_decompress_woff_too_short(self):
        """WOFF data too short returns None."""
        loader = FontLoader()

        result = loader._decompress_woff(b"wOFF" + b"\x00" * 10)  # < 44 bytes
        assert result is None

    def test_decompress_woff_exceeds_size_limit(self):
        """WOFF with decompressed size exceeding limit returns None."""
        # Create WOFF header with huge totalSfntSize
        woff_header = (
            b"wOFF" +                          # signature
            b"\x00\x01\x00\x00" +              # flavor (TTF)
            b"\x00\x00\x00\x2C" +              # length (44 bytes)
            b"\x00\x01" +                      # numTables (1)
            b"\x00\x00" +                      # reserved
            (20 * 1024 * 1024).to_bytes(4, "big") +  # totalSfntSize (20 MB)
            b"\x00" * 24                       # rest of header
        )

        loader = FontLoader(max_size=10 * 1024 * 1024)  # 10 MB limit
        result = loader._decompress_woff(woff_header)

        assert result is None

    @pytest.mark.skipif(
        not FONTFORGE_AVAILABLE,
        reason="FontForge required for WOFF2"
    )
    def test_decompress_woff2_integration(self):
        """WOFF2 decompression integration test (requires real font)."""
        # This test verifies that WOFF2 decompression works when
        # FontForge is available.
        # A comprehensive test would need a real WOFF2 font file.

        loader = FontLoader()

        # Test with invalid WOFF2 data
        invalid_woff2 = b"wOF2" + b"\x00" * 100
        result = loader._decompress_woff2(invalid_woff2)
        # Should fail gracefully
        assert result is None

        # NOTE: Full WOFF2 round-trip test would require:
        # 1. A valid WOFF2 font file (not easy to create in tests)
        # 2. Or using a real font from Google Fonts etc.
        # For now, we verify the code path works and fails gracefully

    def test_decompress_woff2_without_dependencies(self, monkeypatch):
        """WOFF2 decompression without dependencies returns None."""
        monkeypatch.setattr("svg2ooxml.services.fonts.loader.FONTFORGE_AVAILABLE", False)

        loader = FontLoader()
        result = loader._decompress_woff2(b"wOF2" + b"\x00" * 100)

        assert result is None

    def test_loaded_font_post_init_size(self):
        """LoadedFont calculates size_bytes if not provided."""
        data = b"\x00\x01\x00\x00" + b"\x00" * 100
        font = LoadedFont(
            data=data,
            format="ttf",
            source_url="test.ttf"
        )

        assert font.size_bytes == len(data)

    def test_loaded_font_with_explicit_size(self):
        """LoadedFont uses explicit size_bytes if provided."""
        data = b"\x00" * 100
        font = LoadedFont(
            data=data,
            format="ttf",
            source_url="test.ttf",
            size_bytes=12345  # Explicit size
        )

        assert font.size_bytes == 12345  # Not len(data)
