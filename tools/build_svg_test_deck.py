"""Build a PPTX with embedded SVG images (one per slide) for manual testing.

Each slide contains an SVG via the Office 2016+ svgBlip extension, with a
small PNG fallback for older versions. Open in PowerPoint and use
"Convert to Shape" / Ungroup to test PowerPoint's SVG conversion quality.
"""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

# -- Namespaces ---------------------------------------------------------------

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "asvg": "http://schemas.microsoft.com/office/drawing/2016/SVG/main",
}

REL_SLIDE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
REL_SLIDE_LAYOUT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
REL_SLIDE_MASTER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster"
REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
REL_THEME = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
SVG_BLIP_URI = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"

# Slide dimensions in EMU (10" x 7.5" at 914400 EMU/inch)
SLIDE_W = 9144000
SLIDE_H = 6858000
MARGIN = 457200  # 0.5 inch


def _minimal_png_1x1() -> bytes:
    """Return a valid 1x1 white PNG (smallest possible)."""

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        import zlib
        raw = chunk_type + data
        return struct.pack(">I", len(data)) + raw + struct.pack(">I", zlib.crc32(raw) & 0xFFFFFFFF)

    import zlib
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    scanline = b"\x00\xff\xff\xff"
    idat = zlib.compress(scanline)
    return header + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def _el(tag: str, attrib: dict | None = None, text: str | None = None) -> ET.Element:
    elem = ET.Element(tag, attrib or {})
    if text is not None:
        elem.text = text
    return elem


def _sub(parent: ET.Element, tag: str, attrib: dict | None = None, text: str | None = None) -> ET.Element:
    elem = ET.SubElement(parent, tag, attrib or {})
    if text is not None:
        elem.text = text
    return elem


def _to_xml(elem: ET.Element) -> bytes:
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(elem, encoding="unicode").encode("utf-8")


def _build_content_types(slide_count: int) -> bytes:
    root = _el(f"{{{NS['ct']}}}Types")
    _sub(root, f"{{{NS['ct']}}}Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
    _sub(root, f"{{{NS['ct']}}}Default", {"Extension": "xml", "ContentType": "application/xml"})
    _sub(root, f"{{{NS['ct']}}}Default", {"Extension": "png", "ContentType": "image/png"})
    _sub(root, f"{{{NS['ct']}}}Default", {"Extension": "svg", "ContentType": "image/svg+xml"})
    _sub(root, f"{{{NS['ct']}}}Override", {"PartName": "/ppt/presentation.xml", "ContentType": "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"})
    _sub(root, f"{{{NS['ct']}}}Override", {"PartName": "/ppt/slideMasters/slideMaster1.xml", "ContentType": "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"})
    _sub(root, f"{{{NS['ct']}}}Override", {"PartName": "/ppt/slideLayouts/slideLayout1.xml", "ContentType": "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"})
    _sub(root, f"{{{NS['ct']}}}Override", {"PartName": "/ppt/theme/theme1.xml", "ContentType": "application/vnd.openxmlformats-officedocument.theme+xml"})
    for i in range(1, slide_count + 1):
        _sub(root, f"{{{NS['ct']}}}Override", {"PartName": f"/ppt/slides/slide{i}.xml", "ContentType": "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"})
    return _to_xml(root)


def _build_rels() -> bytes:
    root = _el(f"{{{NS['rel']}}}Relationships")
    _sub(root, f"{{{NS['rel']}}}Relationship", {"Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", "Target": "ppt/presentation.xml"})
    return _to_xml(root)


def _build_presentation(slide_count: int) -> bytes:
    root = _el(f"{{{NS['p']}}}presentation", {
        f"{{{NS['r']}}}id": "",
    })
    sldMasterIdLst = _sub(root, f"{{{NS['p']}}}sldMasterIdLst")
    _sub(sldMasterIdLst, f"{{{NS['p']}}}sldMasterId", {"id": "2147483648", f"{{{NS['r']}}}id": "rId1"})
    sldIdLst = _sub(root, f"{{{NS['p']}}}sldIdLst")
    for i in range(slide_count):
        _sub(sldIdLst, f"{{{NS['p']}}}sldId", {"id": str(256 + i), f"{{{NS['r']}}}id": f"rId{i + 10}"})
    sldSz = _sub(root, f"{{{NS['p']}}}sldSz", {"cx": str(SLIDE_W), "cy": str(SLIDE_H)})
    return _to_xml(root)


def _build_presentation_rels(slide_count: int) -> bytes:
    root = _el(f"{{{NS['rel']}}}Relationships")
    _sub(root, f"{{{NS['rel']}}}Relationship", {"Id": "rId1", "Type": REL_SLIDE_MASTER, "Target": "slideMasters/slideMaster1.xml"})
    _sub(root, f"{{{NS['rel']}}}Relationship", {"Id": "rId2", "Type": REL_THEME, "Target": "theme/theme1.xml"})
    for i in range(slide_count):
        _sub(root, f"{{{NS['rel']}}}Relationship", {"Id": f"rId{i + 10}", "Type": REL_SLIDE, "Target": f"slides/slide{i + 1}.xml"})
    return _to_xml(root)


def _build_slide_master() -> bytes:
    root = _el(f"{{{NS['p']}}}sldMaster")
    cSld = _sub(root, f"{{{NS['p']}}}cSld")
    _sub(cSld, f"{{{NS['p']}}}bg")
    _sub(cSld, f"{{{NS['p']}}}spTree")
    sldLayoutIdLst = _sub(root, f"{{{NS['p']}}}sldLayoutIdLst")
    _sub(sldLayoutIdLst, f"{{{NS['p']}}}sldLayoutId", {"id": "2147483649", f"{{{NS['r']}}}id": "rId1"})
    return _to_xml(root)


def _build_slide_master_rels() -> bytes:
    root = _el(f"{{{NS['rel']}}}Relationships")
    _sub(root, f"{{{NS['rel']}}}Relationship", {"Id": "rId1", "Type": REL_SLIDE_LAYOUT, "Target": "../slideLayouts/slideLayout1.xml"})
    _sub(root, f"{{{NS['rel']}}}Relationship", {"Id": "rId2", "Type": REL_THEME, "Target": "../theme/theme1.xml"})
    return _to_xml(root)


def _build_slide_layout() -> bytes:
    root = _el(f"{{{NS['p']}}}sldLayout", {"type": "blank"})
    cSld = _sub(root, f"{{{NS['p']}}}cSld")
    _sub(cSld, f"{{{NS['p']}}}spTree")
    return _to_xml(root)


def _build_slide_layout_rels() -> bytes:
    root = _el(f"{{{NS['rel']}}}Relationships")
    _sub(root, f"{{{NS['rel']}}}Relationship", {"Id": "rId1", "Type": REL_SLIDE_MASTER, "Target": "../slideMasters/slideMaster1.xml"})
    return _to_xml(root)


def _build_theme() -> bytes:
    root = _el(f"{{{NS['a']}}}theme", {"name": "SVG Test"})
    _sub(root, f"{{{NS['a']}}}themeElements")
    return _to_xml(root)


def _build_slide(svg_name: str, slide_index: int) -> bytes:
    """Build slide XML with a title text box and an SVG picture."""
    root = _el(f"{{{NS['p']}}}sld")
    cSld = _sub(root, f"{{{NS['p']}}}cSld")
    spTree = _sub(cSld, f"{{{NS['p']}}}spTree")

    # Group shape properties (required)
    grpSpPr = _sub(spTree, f"{{{NS['p']}}}grpSpPr")
    xfrm = _sub(grpSpPr, f"{{{NS['a']}}}xfrm")
    _sub(xfrm, f"{{{NS['a']}}}off", {"x": "0", "y": "0"})
    _sub(xfrm, f"{{{NS['a']}}}ext", {"cx": "0", "cy": "0"})
    _sub(xfrm, f"{{{NS['a']}}}chOff", {"x": "0", "y": "0"})
    _sub(xfrm, f"{{{NS['a']}}}chExt", {"cx": "0", "cy": "0"})

    # Title text box
    sp = _sub(spTree, f"{{{NS['p']}}}sp")
    nvSpPr = _sub(sp, f"{{{NS['p']}}}nvSpPr")
    _sub(nvSpPr, f"{{{NS['p']}}}cNvPr", {"id": "2", "name": "Title"})
    _sub(nvSpPr, f"{{{NS['p']}}}cNvSpPr")
    _sub(nvSpPr, f"{{{NS['p']}}}nvPr")
    spPr = _sub(sp, f"{{{NS['p']}}}spPr")
    txfrm = _sub(spPr, f"{{{NS['a']}}}xfrm")
    _sub(txfrm, f"{{{NS['a']}}}off", {"x": str(MARGIN), "y": "100000"})
    _sub(txfrm, f"{{{NS['a']}}}ext", {"cx": str(SLIDE_W - 2 * MARGIN), "cy": "400000"})
    _sub(spPr, f"{{{NS['a']}}}prstGeom", {"prst": "rect"})
    txBody = _sub(sp, f"{{{NS['p']}}}txBody")
    _sub(txBody, f"{{{NS['a']}}}bodyPr")
    p_elem = _sub(txBody, f"{{{NS['a']}}}p")
    rPr = {"lang": "en-US", "sz": "1400", "b": "1"}
    r_elem = _sub(p_elem, f"{{{NS['a']}}}r")
    _sub(r_elem, f"{{{NS['a']}}}rPr", rPr)
    _sub(r_elem, f"{{{NS['a']}}}t").text = f"Slide {slide_index + 1}: {svg_name}"

    # SVG picture — rId2 = PNG fallback, rId3 = SVG
    pic = _sub(spTree, f"{{{NS['p']}}}pic")
    nvPicPr = _sub(pic, f"{{{NS['p']}}}nvPicPr")
    _sub(nvPicPr, f"{{{NS['p']}}}cNvPr", {"id": "3", "name": svg_name})
    _sub(nvPicPr, f"{{{NS['p']}}}cNvPicPr")
    _sub(nvPicPr, f"{{{NS['p']}}}nvPr")
    blipFill = _sub(pic, f"{{{NS['p']}}}blipFill")
    blip = _sub(blipFill, f"{{{NS['a']}}}blip", {f"{{{NS['r']}}}embed": "rId2"})
    # Add svgBlip extension
    extLst = _sub(blip, f"{{{NS['a']}}}extLst")
    ext = _sub(extLst, f"{{{NS['a']}}}ext", {"uri": SVG_BLIP_URI})
    _sub(ext, f"{{{NS['asvg']}}}svgBlip", {f"{{{NS['r']}}}embed": "rId3"})
    stretch = _sub(blipFill, f"{{{NS['a']}}}stretch")
    _sub(stretch, f"{{{NS['a']}}}fillRect")
    picSpPr = _sub(pic, f"{{{NS['p']}}}spPr")
    picXfrm = _sub(picSpPr, f"{{{NS['a']}}}xfrm")
    # Center the SVG on the slide (480x360 W3C default → scale to fill)
    pic_w = SLIDE_W - 2 * MARGIN
    pic_h = SLIDE_H - 1200000  # leave room for title
    _sub(picXfrm, f"{{{NS['a']}}}off", {"x": str(MARGIN), "y": "600000"})
    _sub(picXfrm, f"{{{NS['a']}}}ext", {"cx": str(pic_w), "cy": str(pic_h)})
    _sub(picSpPr, f"{{{NS['a']}}}prstGeom", {"prst": "rect"})

    return _to_xml(root)


def _build_slide_rels() -> bytes:
    """Slide relationships: rId1=layout, rId2=PNG fallback, rId3=SVG."""
    root = _el(f"{{{NS['rel']}}}Relationships")
    _sub(root, f"{{{NS['rel']}}}Relationship", {"Id": "rId1", "Type": REL_SLIDE_LAYOUT, "Target": "../slideLayouts/slideLayout1.xml"})
    # rId2 and rId3 will be added per-slide (PNG and SVG targets)
    return root  # return element, not bytes — caller adds media refs


def build_deck(svg_files: list[Path], output_path: Path) -> None:
    """Build a PPTX with one SVG per slide."""
    fallback_png = _minimal_png_1x1()
    slide_count = len(svg_files)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _build_content_types(slide_count))
        zf.writestr("_rels/.rels", _build_rels())
        zf.writestr("ppt/presentation.xml", _build_presentation(slide_count))
        zf.writestr("ppt/_rels/presentation.xml.rels", _build_presentation_rels(slide_count))
        zf.writestr("ppt/slideMasters/slideMaster1.xml", _build_slide_master())
        zf.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", _build_slide_master_rels())
        zf.writestr("ppt/slideLayouts/slideLayout1.xml", _build_slide_layout())
        zf.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _build_slide_layout_rels())
        zf.writestr("ppt/theme/theme1.xml", _build_theme())

        for i, svg_path in enumerate(svg_files):
            slide_num = i + 1
            svg_name = svg_path.stem

            # Add media files
            zf.writestr(f"ppt/media/fallback{slide_num}.png", fallback_png)
            zf.writestr(f"ppt/media/{svg_name}.svg", svg_path.read_bytes())

            # Build slide
            zf.writestr(f"ppt/slides/slide{slide_num}.xml", _build_slide(svg_name, i))

            # Build slide rels with media references
            rels_root = _build_slide_rels()
            _sub(rels_root, f"{{{NS['rel']}}}Relationship", {
                "Id": "rId2",
                "Type": REL_IMAGE,
                "Target": f"../media/fallback{slide_num}.png",
            })
            _sub(rels_root, f"{{{NS['rel']}}}Relationship", {
                "Id": "rId3",
                "Type": REL_IMAGE,
                "Target": f"../media/{svg_name}.svg",
            })
            zf.writestr(f"ppt/slides/_rels/slide{slide_num}.xml.rels", _to_xml(rels_root))

    print(f"Created {output_path} with {slide_count} slides")


# -- SVG selection: pick diverse test cases ------------------------------------

DECK_1_SVGS = [
    # Basic shapes
    "shapes-rect-01-t.svg",
    # Linear + radial gradients
    "pservers-grad-01-b.svg",
    "pservers-grad-02-b.svg",
    # Gradient transforms and spread
    "pservers-grad-08-b.svg",
    # Text basics
    "text-intro-01-t.svg",
    # Text positioning (dx/dy)
    "text-tspan-01-b.svg",
    # Opacity
    "masking-opacity-01-b.svg",
    # Clip paths
    "masking-path-01-b.svg",
    # Filters (gaussian blur)
    "filters-gauss-01-b.svg",
    # Filters (lighting)
    "filters-diffuse-01-f.svg",
    # Painting (fill rules, stroke)
    "painting-fill-01-t.svg",
    "painting-stroke-04-t.svg",
]

DECK_2_SVGS = [
    # Edge cases — probing UNKNOWN PowerPoint "Convert to Shape" behaviors.
    # Each tests a feature where we don't know how PPT handles it.
    "pservers-pattern-01-b.svg",  # pattern fills on shapes + text — does PPT support <pattern>?
    "painting-marker-01-f.svg",   # SVG markers/arrowheads — does PPT map to DrawingML line endings?
    "struct-use-01-t.svg",        # <use> element with inherited style — does PPT expand correctly?
    "struct-symbol-01-b.svg",     # <symbol> + <use> instancing — does PPT handle symbol viewBox?
    "text-path-01-b.svg",         # text on a curved path — does PPT support textPath at all?
    "text-deco-01-b.svg",         # text-decoration (underline/overline/line-through)
    "text-spacing-01-b.svg",      # letter-spacing and word-spacing on text
    "text-bidi-01-t.svg",         # right-to-left (Arabic) text direction
    "masking-mask-01-b.svg",      # <mask> element (luminance mask, not just clip-path)
    "coords-viewattr-01-b.svg",   # viewBox with non-default preserveAspectRatio + nested viewports
    "pservers-grad-03-b.svg",     # gradient spreadMethod (reflect/repeat) — does PPT handle these?
    "paths-data-12-t.svg",        # cubic bezier poly-curves with implicit S commands
]

DECK_3_SVGS = [
    # Remaining unknowns — probing PPT behaviors not yet tested.
    "pservers-grad-10-b.svg",     # spreadMethod (pad/reflect/repeat) — the correct test
    "pservers-grad-06-b.svg",     # gradientTransform
    "painting-stroke-07-t.svg",   # stroke-dashoffset
    "painting-fill-03-t.svg",     # fill with inherit + currentColor
    "masking-path-04-b.svg",      # nested clip paths
    "text-tspan-02-b.svg",        # multi-line tspan with absolute positioning
    "render-groups-01-b.svg",     # group opacity (opacity on <g>)
    "painting-stroke-10-t.svg",   # zero-length stroke linecaps
    "coords-trans-09-t.svg",      # nested group transforms
    "struct-group-03-t.svg",      # group with transform + opacity combined
]

SELECTED_SVGS = DECK_1_SVGS


def main() -> None:
    import sys

    svg_dir = Path(__file__).resolve().parents[1] / "tests" / "svg"
    output_dir = Path(__file__).resolve().parents[1] / "tmp"
    output_dir.mkdir(parents=True, exist_ok=True)

    deck = "1"
    if len(sys.argv) > 1 and sys.argv[1] in ("1", "2", "3"):
        deck = sys.argv[1]

    if deck == "3":
        svg_list = DECK_3_SVGS
        output = output_dir / "svg_test_deck_3.pptx"
    elif deck == "2":
        svg_list = DECK_2_SVGS
        output = output_dir / "svg_test_deck_2.pptx"
    else:
        svg_list = DECK_1_SVGS
        output = output_dir / "svg_test_deck.pptx"

    svg_files = []
    for name in svg_list:
        path = svg_dir / name
        if path.exists():
            svg_files.append(path)
        else:
            print(f"Warning: {name} not found, skipping")

    if not svg_files:
        print("No SVG files found!")
        return

    build_deck(svg_files, output)
    print(f"\nOpen in PowerPoint: {output}")
    print("Right-click each SVG → 'Convert to Shape' or Ungroup to test conversion")


if __name__ == "__main__":
    main()
