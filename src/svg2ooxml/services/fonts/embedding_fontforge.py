"""FontForge glyph selection and subsetting helpers."""

from __future__ import annotations

import logging

from svg2ooxml.services.fonts.fontforge_utils import generate_font_bytes

logger = logging.getLogger(__name__)


class FontForgeSubsetMixin:
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
                        selection.select(("more",), glyph_name)
                    else:
                        selection.select(glyph_name)
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
                        selection.select(("more",), glyph.glyphname)
                    else:
                        selection.select(glyph.glyphname)
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
                        selection.select(("more",), glyph.glyphname)
                    else:
                        selection.select(glyph.glyphname)
                        selected_any = True
                    break
                except Exception:
                    continue
        return selected_any

    @staticmethod
    def _glyph_unicode_sequences(glyph: object) -> list[str]:
        sequences: list[str] = []

        def add_sequence(value: object) -> None:
            seq = FontForgeSubsetMixin._coerce_unicode_sequence(value)
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


__all__ = ["FontForgeSubsetMixin"]
