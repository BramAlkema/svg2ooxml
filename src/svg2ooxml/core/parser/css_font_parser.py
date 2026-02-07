"""Parser for CSS @font-face rules using tinycss2."""
from __future__ import annotations

import logging
from typing import Any, cast

import tinycss2  # type: ignore[import-untyped]
from lxml import etree  # type: ignore[import-untyped]
from tinycss2.ast import (  # type: ignore[import-untyped]
    AtRule,
    Declaration,
    FunctionBlock,
    StringToken,
    URLToken,
)

from svg2ooxml.ir.fonts import FontFaceRule, FontFaceSrc

logger = logging.getLogger(__name__)


class CSSFontFaceParser:
    """Parse @font-face rules from SVG <style> elements."""

    def parse_stylesheets(self, svg_root: etree._Element) -> list[FontFaceRule]:
        """Extract all @font-face rules from <style> elements in SVG.

        Args:
            svg_root: Root SVG element

        Returns:
            List of parsed FontFaceRule objects
        """
        font_rules: list[FontFaceRule] = []

        # Find all <style> elements
        style_elements = svg_root.xpath(
            ".//svg:style",
            namespaces={"svg": "http://www.w3.org/2000/svg"}
        )

        for style_elem in style_elements:
            css_text = style_elem.text or ""
            rules = self._parse_css_text(css_text)
            font_rules.extend(rules)

        if font_rules:
            logger.debug(
                f"Parsed {len(font_rules)} @font-face rule(s) from "
                f"{len(style_elements)} <style> element(s)"
            )

        return font_rules

    def _parse_css_text(self, css_text: str) -> list[FontFaceRule]:
        """Parse CSS text and extract @font-face rules.

        Args:
            css_text: CSS stylesheet text

        Returns:
            List of FontFaceRule objects
        """
        rules: list[FontFaceRule] = []

        # Parse CSS using tinycss2 with skip options for robustness
        stylesheet = tinycss2.parse_stylesheet(
            css_text,
            skip_whitespace=True,
            skip_comments=True
        )

        for rule in stylesheet:
            if isinstance(rule, AtRule) and rule.at_keyword.lower() == "font-face":
                try:
                    font_rule = self._parse_font_face_rule(rule)
                    if font_rule:
                        rules.append(font_rule)
                except Exception as e:
                    logger.warning(f"Skipping invalid @font-face rule: {e}")
                    continue

        return rules

    def _parse_font_face_rule(self, rule: AtRule) -> FontFaceRule | None:
        """Parse a single @font-face { ... } block.

        Args:
            rule: tinycss2 AtRule node

        Returns:
            FontFaceRule or None if invalid
        """
        # Parse declarations inside @font-face block
        declarations = tinycss2.parse_declaration_list(
            rule.content,
            skip_whitespace=True,
            skip_comments=True
        )

        # Extract descriptors
        family = None
        src: list[FontFaceSrc] = []
        weight = "normal"
        style = "normal"
        display = "auto"
        unicode_range = None

        for decl in declarations:
            if not isinstance(decl, Declaration):
                continue

            name = decl.name.lower()

            if name == "font-family":
                family = self._extract_family_name(decl.value)
            elif name == "src":
                src = self._parse_src_descriptor(decl.value)
            elif name == "font-weight":
                weight = tinycss2.serialize(decl.value).strip()
            elif name == "font-style":
                style = tinycss2.serialize(decl.value).strip()
            elif name == "font-display":
                display = tinycss2.serialize(decl.value).strip()
            elif name == "unicode-range":
                unicode_range = tinycss2.serialize(decl.value).strip()

        # Validate required descriptors
        if not family or not src:
            logger.debug(
                f"Skipping @font-face: missing required descriptor "
                f"(family={bool(family)}, src={bool(src)})"
            )
            return None

        return FontFaceRule(
            family=family,
            src=src,
            weight=weight,
            style=style,
            display=display,
            unicode_range=unicode_range,
        )

    def _extract_family_name(self, tokens: list[Any]) -> str:
        """Extract font-family name from CSS tokens.

        Args:
            tokens: CSS tokens from tinycss2

        Returns:
            Normalized family name (quotes stripped)
        """
        serialized = cast(str, tinycss2.serialize(tokens).strip())
        # Remove quotes
        return serialized.strip('"').strip("'")

    def _parse_src_descriptor(self, tokens: list[Any]) -> list[FontFaceSrc]:
        """Parse src: url(...) format(...), ... descriptor.

        Uses tinycss2 token parsing instead of regex for robustness.

        Args:
            tokens: CSS tokens from tinycss2

        Returns:
            List of FontFaceSrc objects in priority order
        """
        sources: list[FontFaceSrc] = []
        current_src: dict[str, str | None] = {}

        i = 0
        while i < len(tokens):
            token = tokens[i]

            # URLToken (unquoted url() syntax)
            if isinstance(token, URLToken):
                current_src["url"] = token.value

            # url() function (quoted syntax)
            elif isinstance(token, FunctionBlock) and token.name.lower() == "url":
                url = self._extract_url_from_function(token.arguments)
                if url:
                    current_src["url"] = url

            # local() function
            elif isinstance(token, FunctionBlock) and token.name.lower() == "local":
                local_name = tinycss2.serialize(token.arguments).strip()
                local_name = local_name.strip('"').strip("'")
                current_src["url"] = f"local({local_name})"

            # format() function
            elif isinstance(token, FunctionBlock) and token.name.lower() == "format":
                format_val = tinycss2.serialize(token.arguments).strip()
                format_val = format_val.strip('"').strip("'")
                current_src["format"] = format_val

            # tech() function (SVG2)
            elif isinstance(token, FunctionBlock) and token.name.lower() == "tech":
                tech_val = tinycss2.serialize(token.arguments).strip()
                tech_val = tech_val.strip('"').strip("'")
                current_src["tech"] = tech_val

            # Comma separator - end of current src
            elif hasattr(token, 'type') and token.type == 'literal' and token.value == ',':
                url = current_src.get("url")
                if url:
                    sources.append(FontFaceSrc(
                        url=url,
                        format=current_src.get("format"),
                        tech=current_src.get("tech"),
                    ))
                current_src = {}

            i += 1

        # Add final src
        url = current_src.get("url")
        if url:
            sources.append(FontFaceSrc(
                url=url,
                format=current_src.get("format"),
                tech=current_src.get("tech"),
            ))

        return sources

    def _extract_url_from_function(self, arguments: list[Any]) -> str | None:
        """Extract URL string from url() function arguments.

        Args:
            arguments: Token list from url() function

        Returns:
            URL string or None
        """
        for token in arguments:
            if isinstance(token, (StringToken, URLToken)):
                return cast(str, token.value)
        return None
