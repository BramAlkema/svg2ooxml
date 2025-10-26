"""XML parsing utilities that produce `SvgDocument` instances."""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any

from lxml import etree

from .converter import convert_document
from .options import Options
from .tree import SvgDocument


def _read_bytes(source: Path | str | bytes) -> bytes:
    if isinstance(source, bytes):
        return source

    path = Path(source)
    return path.read_bytes()


def _maybe_decompress(data: bytes) -> bytes:
    if data.startswith(b"\x1f\x8b"):
        return gzip.decompress(data)
    return data


def parse_svg_bytes(data: bytes, *, options: Options) -> SvgDocument:
    """Parse an SVG document from bytes, handling SVGZ if necessary."""
    decoded = _maybe_decompress(data)
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        remove_comments=False,
        remove_pis=False,
        huge_tree=False,
    )
    root_element = etree.fromstring(decoded, parser=parser)
    return convert_document(root_element, options)


def parse_svg_string(text: str, *, options: Options) -> SvgDocument:
    return parse_svg_bytes(text.encode("utf-8"), options=options)


def parse_svg_file(path: Path | str, *, options: Options) -> SvgDocument:
    data = _read_bytes(path)
    doc = parse_svg_bytes(data, options=options)
    doc.base_dir = str(Path(path).resolve().parent)
    return doc

