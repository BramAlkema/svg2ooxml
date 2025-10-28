"""Utilities for evaluating SVG <switch> elements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from lxml import etree


@dataclass(frozen=True)
class SwitchEvaluator:
    """Selects the appropriate child of an SVG <switch> element."""

    system_languages: Sequence[str]
    supported_features: Iterable[str]

    def select_child(self, switch_element: etree._Element) -> etree._Element | None:
        selected = None
        fallback = None
        for child in switch_element:
            if not isinstance(child.tag, str):
                continue
            if self._child_matches(child):
                selected = child
                break
            if fallback is None and not self._child_has_tests(child):
                fallback = child
        return selected if selected is not None else fallback

    # ------------------------------------------------------------------
    # Matching helpers
    # ------------------------------------------------------------------

    def _child_matches(self, child: etree._Element) -> bool:
        if not self._child_has_tests(child):
            return False

        if not self._features_match(child):
            return False
        if not self._extensions_match(child):
            return False
        if not self._formats_match(child):
            return False
        if not self._language_match(child):
            return False
        return True

    @staticmethod
    def _child_has_tests(child: etree._Element) -> bool:
        return any(
            key in child.attrib
            for key in ("systemLanguage", "requiredFeatures", "requiredExtensions", "requiredFormats")
        )

    def _features_match(self, child: etree._Element) -> bool:
        raw = child.get("requiredFeatures")
        if not raw:
            return True
        required = {token for token in self._tokenize(raw) if token}
        if not required:
            return False
        supported = set(self.supported_features)
        return required <= supported

    def _extensions_match(self, child: etree._Element) -> bool:
        raw = child.get("requiredExtensions")
        if not raw:
            return True
        return not any(self._tokenize(raw))

    def _formats_match(self, child: etree._Element) -> bool:
        raw = child.get("requiredFormats")
        if not raw:
            return True
        return not any(self._tokenize(raw))

    def _language_match(self, child: etree._Element) -> bool:
        raw = child.get("systemLanguage")
        if not raw:
            return True
        languages = [token for token in self._tokenize(raw) if token]
        if not languages:
            return False
        return any(self._matches_system_language(token) for token in languages)

    @staticmethod
    def _tokenize(raw: str) -> list[str]:
        tokens: list[str] = []
        for part in raw.replace(",", " ").split():
            token = part.strip()
            if token:
                tokens.append(token)
        return tokens

    def _matches_system_language(self, candidate: str) -> bool:
        normalized = candidate.replace("_", "-").lower()
        languages = tuple(self.system_languages) or ("en",)

        for lang in languages:
            lang_norm = lang.replace("_", "-").lower()
            if normalized == lang_norm:
                return True
            if "-" in lang_norm and normalized == lang_norm.split("-", 1)[0]:
                return True
        return False


__all__ = ["SwitchEvaluator"]
