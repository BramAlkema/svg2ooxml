"""XML parsing utilities that produce `SvgDocument` instances."""

from __future__ import annotations

from pathlib import Path

from svg2ooxml.common.boundaries import decompress_svgz_bytes, parse_xml_bytes
from svg2ooxml.core.resvg.parser.converter import convert_document
from svg2ooxml.core.resvg.parser.options import Options
from svg2ooxml.core.resvg.parser.tree import SvgDocument


def _read_bytes(source: Path | str | bytes) -> bytes:
    if isinstance(source, bytes):
        return source

    path = Path(source)
    return path.read_bytes()


def parse_svg_bytes(data: bytes, *, options: Options) -> SvgDocument:
    """Parse an SVG document from bytes, handling SVGZ if necessary."""
    decoded = decompress_svgz_bytes(data)
    root_element = parse_xml_bytes(
        decoded,
        description="resvg SVG XML",
        remove_comments=False,
        remove_pis=False,
        recover=False,
    )
    return convert_document(root_element, options)


def parse_svg_string(text: str, *, options: Options) -> SvgDocument:
    return parse_svg_bytes(text.encode("utf-8"), options=options)


def parse_svg_file(path: Path | str, *, options: Options) -> SvgDocument:
    data = _read_bytes(path)
    doc = parse_svg_bytes(data, options=options)
    doc.base_dir = str(Path(path).resolve().parent)
    return doc
