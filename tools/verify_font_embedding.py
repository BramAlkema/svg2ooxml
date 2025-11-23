#!/usr/bin/env python3
"""Inspect embedded font parts inside a PPTX file."""

from __future__ import annotations

import argparse
import struct
import sys
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

from lxml import etree


REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_DOC_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path, help="Path to the PPTX file to inspect.")
    return parser.parse_args()


def _read_zip(path: Path) -> ZipFile:
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        sys.exit(2)
    return ZipFile(path)


def _list_font_parts(archive: ZipFile) -> list[str]:
    return sorted(name for name in archive.namelist() if name.startswith("ppt/fonts/"))


def _inspect_eot_payload(name: str, data: bytes) -> dict[str, object]:
    eot_size = struct.unpack_from("<L", data, 0)[0]
    font_size = struct.unpack_from("<L", data, 4)[0]
    magic = struct.unpack_from("<H", data, 34)[0]
    return {
        "part": name,
        "size": len(data),
        "declared_size": eot_size,
        "font_size": font_size,
        "magic_ok": magic == 0x504C,
    }


def _load_presentation_metadata(archive: ZipFile) -> dict[str, dict[str, str]]:
    root = etree.fromstring(archive.read("ppt/presentation.xml"))
    ns = {"p": P_NS, "r": R_DOC_NS}
    fonts: dict[str, dict[str, str]] = {}
    for embedded in root.findall(".//p:embeddedFont", ns):
        family = embedded.find("p:font", ns).get("typeface")
        font_key = embedded.find("p:fontKey", ns)
        guid = font_key.get("guid") if font_key is not None else ""
        styles = {}
        for tag in ("regular", "bold", "italic", "boldItalic"):
            node = embedded.find(f"p:{tag}", ns)
            if node is not None:
                styles[tag] = node.get(f"{{{R_DOC_NS}}}id")
        fonts[family] = {"guid": guid, **styles}
    return fonts


def _load_relationships(archive: ZipFile) -> dict[str, str]:
    rels_root = etree.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
    rels = {}
    for rel in rels_root.findall(f"{{{REL_NS}}}Relationship"):
        if rel.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font":
            rels[rel.get("Id")] = rel.get("Target")
    return rels


def _main() -> None:
    args = _parse_args()
    with _read_zip(args.pptx) as archive:

        font_parts = _list_font_parts(archive)
        if not font_parts:
            print("No embedded fonts found.")
            return

        print("Embedded font parts:")
        for name in font_parts:
            info = _inspect_eot_payload(name, archive.read(name))
            status = "OK" if info["magic_ok"] and info["size"] == info["declared_size"] else "WARN"
            print(
                f"  - {Path(name).name}: {info['size']} bytes "
                f"(declared {info['declared_size']}), EOT magic={info['magic_ok']} [{status}]"
            )

        rels = _load_relationships(archive)
        fonts = _load_presentation_metadata(archive)

        print("\nPresentation font entries:")
        for family, meta in fonts.items():
            guid = meta.get("guid") or "(none)"
            print(f"  * {family} (GUID: {guid})")
            for style in ("regular", "bold", "italic", "boldItalic"):
                rel_id = meta.get(style)
                if not rel_id:
                    continue
                target = rels.get(rel_id, "??")
                print(f"      - {style}: {rel_id} -> {target}")


if __name__ == "__main__":
    _main()
