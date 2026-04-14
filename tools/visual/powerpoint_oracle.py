#!/usr/bin/env python3
"""Extract and normalize PowerPoint timing trees into reusable oracle artifacts."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from lxml import etree as ET

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"p": P_NS}
TIMING_TAGS = (
    "set",
    "anim",
    "animMotion",
    "animEffect",
    "animScale",
    "animRot",
    "animClr",
)


@dataclass(frozen=True, slots=True)
class EffectPattern:
    slide_file: str
    container_id: str | None
    node_type: str | None
    preset_id: str | None
    preset_class: str | None
    preset_subtype: str | None
    grp_id: str | None
    child_tags: list[str]
    target_shapes: list[str]
    attr_names: list[str]
    start_delays: list[str]
    behavior_durations: list[str]
    signature: str
    family_signature: str


@dataclass(frozen=True, slots=True)
class SlideOracle:
    slide_file: str
    has_timing: bool
    has_build_list: bool
    tag_counts: dict[str, int]
    effect_patterns: list[EffectPattern]


@dataclass(frozen=True, slots=True)
class DeckOracle:
    deck_name: str
    slug: str
    source_path: str
    slide_count: int
    timing_slide_count: int
    build_list_slide_count: int
    slides: list[SlideOracle]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="PowerPoint files or directories containing PowerPoint files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output directory for extracted oracle artifacts.",
    )
    parser.add_argument(
        "--source-name",
        default="powerpoint-oracle",
        help="Short source label used in the generated manifest.",
    )
    return parser.parse_args()


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = lowered.strip("-")
    return lowered or "deck"


def _collect_pptx_paths(inputs: Sequence[Path]) -> list[Path]:
    found: list[Path] = []
    for input_path in inputs:
        if input_path.is_dir():
            found.extend(sorted(input_path.rglob("*.pptx")))
            continue
        if input_path.suffix.lower() == ".pptx":
            found.append(input_path)
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in found:
        resolved = path.resolve()
        if resolved not in seen and resolved.exists():
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _pretty_xml(element: ET._Element) -> str:
    return ET.tostring(
        element,
        encoding="unicode",
        pretty_print=True,
    )


def _normalize_timing_tree(timing: ET._Element) -> ET._Element:
    normalized = deepcopy(timing)
    id_map: dict[str, str] = {}
    grp_map: dict[str, str] = {}
    spid_map: dict[str, str] = {}

    def map_id(value: str) -> str:
        return id_map.setdefault(value, f"id{len(id_map) + 1}")

    def map_grp(value: str) -> str:
        if value == "0":
            return "0"
        return grp_map.setdefault(value, f"grp{len(grp_map) + 1}")

    def map_spid(value: str) -> str:
        return spid_map.setdefault(value, f"shape{len(spid_map) + 1}")

    for element in normalized.iter():
        if "id" in element.attrib:
            element.set("id", map_id(element.get("id", "")))
        if "grpId" in element.attrib:
            element.set("grpId", map_grp(element.get("grpId", "")))
        if "spid" in element.attrib:
            element.set("spid", map_spid(element.get("spid", "")))

        if ET.QName(element).localname == "tn" and "val" in element.attrib:
            raw = element.get("val", "")
            element.set("val", map_id(raw))

    return normalized


def _collect_unique_text(elements: Iterable[ET._Element]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for element in elements:
        text = (element.text or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return values


def _collect_unique_attrs(elements: Iterable[ET._Element], attribute: str) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for element in elements:
        value = element.get(attribute)
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def _pattern_signature(pattern: EffectPattern) -> str:
    child_sig = "+".join(pattern.child_tags) or "none"
    attr_sig = ",".join(pattern.attr_names) or "-"
    return (
        f"{pattern.node_type or 'none'}|"
        f"{pattern.preset_class or 'none'}|"
        f"{pattern.preset_id or 'none'}|"
        f"{child_sig}|"
        f"{attr_sig}"
    )


def _pattern_family_signature(pattern: EffectPattern) -> str:
    child_sig = "+".join(pattern.child_tags) or "none"
    attr_sig = ",".join(pattern.attr_names) or "-"
    return (
        f"{pattern.node_type or 'none'}|"
        f"{pattern.preset_class or 'none'}|"
        f"{child_sig}|"
        f"{attr_sig}"
    )


def _summarize_effect_patterns(slide_xml: ET._Element, slide_file: str) -> list[EffectPattern]:
    patterns: list[EffectPattern] = []
    containers = slide_xml.xpath(
        ".//p:timing//p:cTn[@presetClass or @nodeType='clickEffect' or @nodeType='withEffect' or @nodeType='afterEffect']",
        namespaces=NS,
    )
    for ctn in containers:
        child_tn_lst = ctn.find("p:childTnLst", NS)
        child_tags = []
        if child_tn_lst is not None:
            child_tags = [ET.QName(child).localname for child in child_tn_lst]

        pattern = EffectPattern(
            slide_file=slide_file,
            container_id=ctn.get("id"),
            node_type=ctn.get("nodeType"),
            preset_id=ctn.get("presetID"),
            preset_class=ctn.get("presetClass"),
            preset_subtype=ctn.get("presetSubtype"),
            grp_id=ctn.get("grpId"),
            child_tags=child_tags,
            target_shapes=_collect_unique_attrs(ctn.xpath(".//p:spTgt", namespaces=NS), "spid"),
            attr_names=_collect_unique_text(
                ctn.xpath(".//p:attrNameLst/p:attrName", namespaces=NS)
            ),
            start_delays=_collect_unique_attrs(
                ctn.xpath("./p:stCondLst/p:cond", namespaces=NS),
                "delay",
            ),
            behavior_durations=_collect_unique_attrs(
                ctn.xpath(".//p:cBhvr/p:cTn", namespaces=NS),
                "dur",
            ),
            signature="",
            family_signature="",
        )
        object.__setattr__(pattern, "signature", _pattern_signature(pattern))
        object.__setattr__(pattern, "family_signature", _pattern_family_signature(pattern))
        patterns.append(pattern)
    return patterns


def _summarize_slide(slide_file: str, slide_xml_text: bytes) -> SlideOracle:
    slide_xml = ET.fromstring(slide_xml_text)
    timing = slide_xml.find("p:timing", NS)
    tag_counts = Counter()
    for tag in TIMING_TAGS:
        tag_counts[tag] = len(slide_xml.xpath(f".//p:{tag}", namespaces=NS))
    return SlideOracle(
        slide_file=slide_file,
        has_timing=timing is not None,
        has_build_list=bool(slide_xml.xpath(".//p:timing/p:bldLst", namespaces=NS)),
        tag_counts=dict(tag_counts),
        effect_patterns=_summarize_effect_patterns(slide_xml, slide_file) if timing is not None else [],
    )


def _extract_deck(deck_path: Path, deck_output_dir: Path) -> DeckOracle:
    deck_output_dir.mkdir(parents=True, exist_ok=True)
    slides: list[SlideOracle] = []

    with zipfile.ZipFile(deck_path) as archive:
        slide_files = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        for slide_file in slide_files:
            slide_name = Path(slide_file).name
            slide_xml_text = archive.read(slide_file)
            slide_summary = _summarize_slide(slide_name, slide_xml_text)
            slides.append(slide_summary)

            slide_xml = ET.fromstring(slide_xml_text)
            timing = slide_xml.find("p:timing", NS)
            if timing is None:
                continue

            slide_dir = deck_output_dir / slide_name.replace(".xml", "")
            slide_dir.mkdir(parents=True, exist_ok=True)
            raw_path = slide_dir / "timing.raw.xml"
            raw_path.write_text(_pretty_xml(timing), encoding="utf-8")

            normalized = _normalize_timing_tree(timing)
            normalized_path = slide_dir / "timing.normalized.xml"
            normalized_path.write_text(_pretty_xml(normalized), encoding="utf-8")

            slide_manifest = slide_dir / "summary.json"
            slide_manifest.write_text(
                json.dumps(asdict(slide_summary), indent=2, sort_keys=True),
                encoding="utf-8",
            )

    return DeckOracle(
        deck_name=deck_path.name,
        slug=_slugify(deck_path.stem),
        source_path=str(deck_path),
        slide_count=len(slides),
        timing_slide_count=sum(1 for slide in slides if slide.has_timing),
        build_list_slide_count=sum(1 for slide in slides if slide.has_build_list),
        slides=slides,
    )


def _build_pattern_index(
    decks: Sequence[DeckOracle],
    *,
    use_family_signature: bool,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for deck in decks:
        for slide in deck.slides:
            for pattern in slide.effect_patterns:
                signature = (
                    pattern.family_signature if use_family_signature else pattern.signature
                )
                grouped[signature].append(
                    {
                        "deck": deck.deck_name,
                        "slide": slide.slide_file,
                        "node_type": pattern.node_type or "",
                        "preset_class": pattern.preset_class or "",
                        "preset_id": pattern.preset_id or "",
                    }
                )
    index: list[dict[str, object]] = []
    for signature, occurrences in sorted(grouped.items()):
        index.append(
            {
                "signature": signature,
                "count": len(occurrences),
                "occurrences": occurrences,
            }
        )
    return index


def _write_summary_markdown(
    *,
    source_name: str,
    decks: Sequence[DeckOracle],
    pattern_index: Sequence[dict[str, object]],
    family_index: Sequence[dict[str, object]],
    output_path: Path,
) -> None:
    lines = [
        f"# PowerPoint Oracle: {source_name}",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "This artifact captures authored PowerPoint timing trees from external sample decks.",
        "It stores raw timing XML, normalized timing XML, and grouped effect signatures.",
        "",
        "## Decks",
        "",
    ]
    for deck in decks:
        lines.append(f"### {deck.deck_name}")
        lines.append("")
        lines.append(f"- Source: `{deck.source_path}`")
        lines.append(f"- Slides: `{deck.slide_count}`")
        lines.append(f"- Slides with `p:timing`: `{deck.timing_slide_count}`")
        lines.append(f"- Slides with `p:bldLst`: `{deck.build_list_slide_count}`")
        pattern_counter = Counter()
        for slide in deck.slides:
            for pattern in slide.effect_patterns:
                pattern_counter[pattern.signature] += 1
        if pattern_counter:
            lines.append("- Signatures:")
            for signature, count in pattern_counter.most_common():
                lines.append(f"  - `{signature}` x{count}")
        lines.append("")

    lines.extend(
        [
            "## Cross-Deck Pattern Index",
            "",
        ]
    )
    for entry in pattern_index:
        lines.append(f"- `{entry['signature']}` x{entry['count']}")
    lines.append("")
    lines.extend(
        [
            "## Cross-Deck Pattern Families",
            "",
        ]
    )
    for entry in family_index:
        lines.append(f"- `{entry['signature']}` x{entry['count']}")
    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    deck_paths = _collect_pptx_paths(args.inputs)
    if not deck_paths:
        raise SystemExit("No .pptx inputs found.")

    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    decks: list[DeckOracle] = []
    for deck_path in deck_paths:
        deck_output_dir = output_dir / _slugify(deck_path.stem)
        decks.append(_extract_deck(deck_path, deck_output_dir))

    manifest = {
        "source_name": args.source_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "decks": [asdict(deck) for deck in decks],
        "pattern_index": _build_pattern_index(decks, use_family_signature=False),
        "pattern_family_index": _build_pattern_index(decks, use_family_signature=True),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_summary_markdown(
        source_name=args.source_name,
        decks=decks,
        pattern_index=manifest["pattern_index"],
        family_index=manifest["pattern_family_index"],
        output_path=output_dir / "README.md",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
