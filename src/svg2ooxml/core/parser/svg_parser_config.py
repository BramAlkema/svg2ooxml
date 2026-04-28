"""Configuration model for the public SVG parser."""

from __future__ import annotations

from dataclasses import dataclass

from svg2ooxml.core.parser.dom_loader import ParserOptions


@dataclass(slots=True)
class ParserConfig:
    """Basic parsing configuration flags."""

    remove_comments: bool = False
    strip_whitespace: bool = False
    recover: bool = True
    remove_blank_text: bool = False
    strip_cdata: bool = False
    resolve_entities: bool = False
    apply_normalization: bool = True
    eager_ir: bool = False

    def to_parser_options(self) -> ParserOptions:
        return ParserOptions(
            remove_comments=self.remove_comments,
            remove_blank_text=self.remove_blank_text,
            strip_cdata=self.strip_cdata,
            recover=self.recover,
            resolve_entities=self.resolve_entities,
        )


__all__ = ["ParserConfig"]
