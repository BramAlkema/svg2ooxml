"""Tests for BiDi text detection utilities."""

from __future__ import annotations

from svg2ooxml.common.conversions.bidi import detect_language_from_script, is_rtl_text


class TestIsRtlText:
    def test_arabic_text_is_rtl(self) -> None:
        assert is_rtl_text("مرحبا بالعالم") is True

    def test_hebrew_text_is_rtl(self) -> None:
        assert is_rtl_text("שלום עולם") is True

    def test_english_text_is_ltr(self) -> None:
        assert is_rtl_text("Hello World") is False

    def test_empty_string_is_not_rtl(self) -> None:
        assert is_rtl_text("") is False

    def test_numbers_only_is_not_rtl(self) -> None:
        assert is_rtl_text("12345") is False

    def test_mixed_mostly_arabic_is_rtl(self) -> None:
        assert is_rtl_text("مرحبا بالعالم Hello") is True

    def test_mixed_mostly_english_is_ltr(self) -> None:
        assert is_rtl_text("Hello World مرحبا") is False

    def test_equal_counts_is_not_rtl(self) -> None:
        # 5 Arabic chars vs 5 Latin chars — not RTL (tie goes to LTR)
        assert is_rtl_text("مرحبا Hello") is False

    def test_punctuation_only_is_not_rtl(self) -> None:
        assert is_rtl_text("... !!!") is False


class TestDetectLanguageFromScript:
    def test_arabic_text_returns_arabic(self) -> None:
        result = detect_language_from_script("مرحبا بالعالم")
        assert result == "ar-SA"

    def test_hebrew_text_returns_hebrew(self) -> None:
        result = detect_language_from_script("שלום עולם")
        assert result == "he-IL"

    def test_english_text_returns_english(self) -> None:
        result = detect_language_from_script("Hello World")
        # May return "en-US" or None depending on Python version
        assert result in ("en-US", None)

    def test_empty_string_returns_none(self) -> None:
        assert detect_language_from_script("") is None

    def test_punctuation_only_returns_none(self) -> None:
        assert detect_language_from_script("...") is None
