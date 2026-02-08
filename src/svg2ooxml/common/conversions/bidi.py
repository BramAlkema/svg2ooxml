"""BiDi (bidirectional) text detection utilities."""

from __future__ import annotations

import unicodedata

# Unicode BiDi categories that indicate right-to-left text
_RTL_CATEGORIES = frozenset({"R", "AL", "AN"})


def is_rtl_text(text: str) -> bool:
    """Detect whether text is predominantly right-to-left.

    Uses Unicode bidirectional character categories to determine direction.
    Returns True if the majority of strong-direction characters are RTL.
    """
    if not text:
        return False
    rtl_count = 0
    ltr_count = 0
    for ch in text:
        bidi = unicodedata.bidirectional(ch)
        if bidi in _RTL_CATEGORIES:
            rtl_count += 1
        elif bidi == "L":
            ltr_count += 1
    return rtl_count > ltr_count


def detect_language_from_script(text: str) -> str | None:
    """Detect a likely language tag from the dominant Unicode script.

    Returns BCP-47 language tags for common RTL scripts, or None
    if the script cannot be confidently determined.
    """
    if not text:
        return None
    script_counts: dict[str, int] = {}
    for ch in text:
        if ch.isspace() or unicodedata.category(ch).startswith("P"):
            continue
        try:
            script = unicodedata.script(ch)
        except (AttributeError, ValueError):
            # unicodedata.script() added in Python 3.13
            # Fall back to bidirectional category for older versions
            bidi = unicodedata.bidirectional(ch)
            if bidi == "AL":
                script = "Arabic"
            elif bidi == "R":
                script = "Hebrew"
            elif bidi == "L":
                script = "Latin"
            else:
                continue
        script_counts[script] = script_counts.get(script, 0) + 1

    if not script_counts:
        return None

    dominant = max(script_counts, key=script_counts.get)
    return _SCRIPT_TO_LANG.get(dominant)


_SCRIPT_TO_LANG: dict[str, str] = {
    "Arabic": "ar-SA",
    "Hebrew": "he-IL",
    "Syriac": "syr",
    "Thaana": "dv-MV",
    "Han": "zh-CN",
    "Hiragana": "ja-JP",
    "Katakana": "ja-JP",
    "Hangul": "ko-KR",
    "Devanagari": "hi-IN",
    "Thai": "th-TH",
    "Latin": "en-US",
    "Cyrillic": "ru-RU",
    "Greek": "el-GR",
}


__all__ = ["detect_language_from_script", "is_rtl_text"]
