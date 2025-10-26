"""Adapter layer that exposes usvg-style normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .parser.options import Options, build_default_options
from .parser.xml_loader import parse_svg_bytes, parse_svg_file, parse_svg_string
from .parser.tree import SvgDocument
from .usvg_tree import Tree, build_tree


class NormalizationError(RuntimeError):
    """Raised when the resvg/usvg normalization pipeline fails."""


@dataclass(slots=True)
class NormalizationResult:
    """Normalized tree output plus the underlying parsed document."""

    document: SvgDocument
    tree: Tree


def _ensure_options(options: Options | None) -> Options:
    if options is not None:
        return options
    return build_default_options()


def normalize_svg_file(path: Path | str, *, options: Options | None = None) -> NormalizationResult:
    """Parse and normalize an SVG document from disk."""
    opts = _ensure_options(options)
    document = parse_svg_file(path, options=opts)
    tree = build_tree(document)
    return NormalizationResult(document=document, tree=tree)


def normalize_svg_string(text: str, *, options: Options | None = None) -> NormalizationResult:
    """Parse and normalize an SVG document from an in-memory string."""
    opts = _ensure_options(options)
    document = parse_svg_string(text, options=opts)
    tree = build_tree(document)
    return NormalizationResult(document=document, tree=tree)


def normalize_svg_bytes(data: bytes, *, options: Options | None = None) -> NormalizationResult:
    """Parse and normalize an SVG document from raw bytes (SVG or SVGZ)."""
    opts = _ensure_options(options)
    document = parse_svg_bytes(data, options=opts)
    tree = build_tree(document)
    return NormalizationResult(document=document, tree=tree)

