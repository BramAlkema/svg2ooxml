"""Generic PPTX builder using the svg2ooxml pipeline.

Two modes:
  embed   — Embed SVGs as svgBlip images for manual PowerPoint testing.
  convert — Run SVGs through the full SVG→DrawingML→PPTX pipeline.

Examples:
  python tools/pptx_builder.py embed --deck 1 -o tmp/svg_test_deck.pptx
  python tools/pptx_builder.py embed file1.svg file2.svg -o out.pptx
  python tools/pptx_builder.py convert file1.svg file2.svg -o out.pptx
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from svg2ooxml.drawingml.assets import AssetRegistry
from svg2ooxml.drawingml.result import DrawingMLRenderResult
from svg2ooxml.io.pptx_assembly import PPTXPackageBuilder

# -- Constants ----------------------------------------------------------------

SLIDE_W = 9_144_000  # 10 in. in EMU
SLIDE_H = 6_858_000  # 7.5 in. in EMU
MARGIN = 457_200  # 0.5 in. in EMU

# The svgBlip extension URI registered by Microsoft (Office 2016+).
SVG_BLIP_URI = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"

# Slide XML template for embed mode.
# Placeholders use $-prefixed names to avoid clashing with XML braces.
_EMBED_SLIDE_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:asvg="http://schemas.microsoft.com/office/drawing/2016/SVG/main">
    <p:cSld>
        <p:spTree>
            <p:nvGrpSpPr>
                <p:cNvPr id="1" name=""/>
                <p:cNvGrpSpPr/>
                <p:nvPr/>
            </p:nvGrpSpPr>
            <p:grpSpPr>
                <a:xfrm>
                    <a:off x="0" y="0"/>
                    <a:ext cx="$SLIDE_W" cy="$SLIDE_H"/>
                    <a:chOff x="0" y="0"/>
                    <a:chExt cx="$SLIDE_W" cy="$SLIDE_H"/>
                </a:xfrm>
            </p:grpSpPr>
            <p:sp>
                <p:nvSpPr>
                    <p:cNvPr id="2" name="Title"/>
                    <p:cNvSpPr/>
                    <p:nvPr/>
                </p:nvSpPr>
                <p:spPr>
                    <a:xfrm>
                        <a:off x="$MARGIN" y="100000"/>
                        <a:ext cx="$TITLE_W" cy="400000"/>
                    </a:xfrm>
                    <a:prstGeom prst="rect"/>
                </p:spPr>
                <p:txBody>
                    <a:bodyPr/>
                    <a:p>
                        <a:r>
                            <a:rPr lang="en-US" sz="1400" b="1"/>
                            <a:t>$TITLE</a:t>
                        </a:r>
                    </a:p>
                </p:txBody>
            </p:sp>
            <p:pic>
                <p:nvPicPr>
                    <p:cNvPr id="3" name="$SVG_NAME"/>
                    <p:cNvPicPr/>
                    <p:nvPr/>
                </p:nvPicPr>
                <p:blipFill>
                    <a:blip r:embed="rId2">
                        <a:extLst>
                            <a:ext uri="$SVG_BLIP_URI">
                                <asvg:svgBlip r:embed="rId3"/>
                            </a:ext>
                        </a:extLst>
                    </a:blip>
                    <a:stretch>
                        <a:fillRect/>
                    </a:stretch>
                </p:blipFill>
                <p:spPr>
                    <a:xfrm>
                        <a:off x="$MARGIN" y="600000"/>
                        <a:ext cx="$PIC_W" cy="$PIC_H"/>
                    </a:xfrm>
                    <a:prstGeom prst="rect"/>
                </p:spPr>
            </p:pic>
        </p:spTree>
    </p:cSld>
    <p:clrMapOvr>
        <a:masterClrMapping/>
    </p:clrMapOvr>
</p:sld>"""

# -- Predefined test decks ----------------------------------------------------

DECK_1_SVGS = [
    "shapes-rect-01-t.svg",
    "pservers-grad-01-b.svg",
    "pservers-grad-02-b.svg",
    "pservers-grad-08-b.svg",
    "text-intro-01-t.svg",
    "text-tspan-01-b.svg",
    "masking-opacity-01-b.svg",
    "masking-path-01-b.svg",
    "filters-gauss-01-b.svg",
    "filters-diffuse-01-f.svg",
    "painting-fill-01-t.svg",
    "painting-stroke-04-t.svg",
]

DECK_2_SVGS = [
    "pservers-pattern-01-b.svg",
    "painting-marker-01-f.svg",
    "struct-use-01-t.svg",
    "struct-symbol-01-b.svg",
    "text-path-01-b.svg",
    "text-deco-01-b.svg",
    "text-spacing-01-b.svg",
    "text-bidi-01-t.svg",
    "masking-mask-01-b.svg",
    "coords-viewattr-01-b.svg",
    "pservers-grad-03-b.svg",
    "paths-data-12-t.svg",
]

DECK_3_SVGS = [
    "pservers-grad-10-b.svg",
    "pservers-grad-06-b.svg",
    "painting-stroke-07-t.svg",
    "painting-fill-03-t.svg",
    "masking-path-04-b.svg",
    "text-tspan-02-b.svg",
    "render-groups-01-b.svg",
    "painting-stroke-10-t.svg",
    "coords-trans-09-t.svg",
    "struct-group-03-t.svg",
]

DECKS = {"1": DECK_1_SVGS, "2": DECK_2_SVGS, "3": DECK_3_SVGS}

# -- Helpers ------------------------------------------------------------------


def _minimal_png_1x1() -> bytes:
    """Return a valid 1x1 white PNG (smallest possible)."""

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        raw = chunk_type + data
        return (
            struct.pack(">I", len(data))
            + raw
            + struct.pack(">I", zlib.crc32(raw) & 0xFFFFFFFF)
        )

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    scanline = b"\x00\xff\xff\xff"
    idat = zlib.compress(scanline)
    return header + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


# -- Embed mode ---------------------------------------------------------------


def _build_embed_slide(svg_path: Path, slide_index: int) -> DrawingMLRenderResult:
    """Build a DrawingMLRenderResult for a single svgBlip slide."""
    svg_name = svg_path.stem
    title_w = SLIDE_W - 2 * MARGIN
    pic_w = SLIDE_W - 2 * MARGIN
    pic_h = SLIDE_H - 1_200_000  # room for title

    slide_xml = (
        _EMBED_SLIDE_TEMPLATE.replace("$SLIDE_W", str(SLIDE_W))
        .replace("$SLIDE_H", str(SLIDE_H))
        .replace("$MARGIN", str(MARGIN))
        .replace("$TITLE_W", str(title_w))
        .replace("$TITLE", xml_escape(f"Slide {slide_index + 1}: {svg_name}"))
        .replace("$SVG_NAME", xml_escape(svg_name))
        .replace("$SVG_BLIP_URI", SVG_BLIP_URI)
        .replace("$PIC_W", str(pic_w))
        .replace("$PIC_H", str(pic_h))
    )

    registry = AssetRegistry()
    registry.add_media(
        relationship_id="rId2",
        filename=f"fallback{slide_index + 1}.png",
        content_type="image/png",
        data=_minimal_png_1x1(),
    )
    registry.add_media(
        relationship_id="rId3",
        filename=f"{svg_name}.svg",
        content_type="image/svg+xml",
        data=svg_path.read_bytes(),
    )

    return DrawingMLRenderResult(
        slide_xml=slide_xml,
        slide_size=(SLIDE_W, SLIDE_H),
        assets=registry.snapshot(),
    )


def embed(svg_paths: list[Path], output: Path) -> Path:
    """Embed SVGs as svgBlip images in a PPTX file."""
    results = [_build_embed_slide(p, i) for i, p in enumerate(svg_paths)]
    builder = PPTXPackageBuilder()
    return builder.build_from_results(results, output)


# -- Convert mode -------------------------------------------------------------


def convert(svg_paths: list[Path], output: Path, *, no_fonts: bool = False) -> Path:
    """Convert SVGs to native DrawingML via the full pipeline."""
    from svg2ooxml.core.pptx_exporter import SvgPageSource, SvgToPptxExporter

    metadata: dict | None = None
    if no_fonts:
        metadata = {"policy_overrides": {"text": {"text.embed_fonts": False}}}

    pages = [
        SvgPageSource(
            svg_text=p.read_text(encoding="utf-8"),
            title=p.stem,
            metadata=metadata,
        )
        for p in svg_paths
    ]
    exporter = SvgToPptxExporter()
    result = exporter.convert_pages(pages, output, parallel=True)
    return result.pptx_path


# -- CLI ----------------------------------------------------------------------


def _resolve_svg_files(args: argparse.Namespace) -> list[Path]:
    """Resolve SVG file paths from CLI args (deck selection or explicit files)."""
    svg_dir = Path(__file__).resolve().parents[1] / "tests" / "svg"

    if hasattr(args, "deck") and args.deck:
        names = DECKS.get(args.deck, DECK_1_SVGS)
        paths = []
        for name in names:
            p = svg_dir / name
            if p.exists():
                paths.append(p)
            else:
                print(f"Warning: {name} not found, skipping", file=sys.stderr)
        return paths

    if hasattr(args, "files") and args.files:
        paths = []
        for f in args.files:
            p = Path(f)
            if not p.exists():
                # Try relative to svg_dir
                alt = svg_dir / p.name
                if alt.exists():
                    p = alt
                else:
                    print(f"Warning: {f} not found, skipping", file=sys.stderr)
                    continue
            paths.append(p)
        return paths

    return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generic PPTX builder using the svg2ooxml pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # embed subcommand
    embed_parser = subparsers.add_parser(
        "embed",
        help="Embed SVGs as svgBlip images for PowerPoint testing.",
    )
    embed_parser.add_argument("files", nargs="*", help="SVG files to embed")
    embed_parser.add_argument("--deck", choices=["1", "2", "3"], help="Use predefined test deck")
    embed_parser.add_argument("-o", "--output", required=True, help="Output PPTX path")

    # convert subcommand
    convert_parser = subparsers.add_parser(
        "convert",
        help="Convert SVGs to native DrawingML via the full pipeline.",
    )
    convert_parser.add_argument("files", nargs="+", help="SVG files to convert")
    convert_parser.add_argument("-o", "--output", required=True, help="Output PPTX path")
    convert_parser.add_argument("--no-fonts", action="store_true", help="Disable font embedding")

    args = parser.parse_args()

    svg_files = _resolve_svg_files(args)
    if not svg_files:
        print("No SVG files found!", file=sys.stderr)
        sys.exit(1)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    if args.command == "embed":
        result_path = embed(svg_files, output)
        print(f"Created {result_path} with {len(svg_files)} slides (embed mode)")
        print("Open in PowerPoint → right-click SVG → 'Convert to Shape' to test")
    elif args.command == "convert":
        result_path = convert(svg_files, output, no_fonts=getattr(args, "no_fonts", False))
        print(f"Created {result_path} with {len(svg_files)} slides (convert mode)")


if __name__ == "__main__":
    main()
