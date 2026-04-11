#!/usr/bin/env python3
"""Analyze SVG filter primitive usage across local corpora."""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from lxml import etree

DEFAULT_INPUTS = (
    Path("tests/corpus"),
    Path("tests/svg"),
    Path("tests/visual/fixtures"),
    Path("tests/assets"),
)
SVG_SUFFIXES = {".svg", ".svgz"}


@dataclass
class FilterUsageReport:
    roots: list[str]
    total_svgs: int
    filtered_svgs: int
    total_filter_elements: int
    total_primitive_instances: int
    primitive_instance_counts: dict[str, int] = field(default_factory=dict)
    primitive_document_counts: dict[str, int] = field(default_factory=dict)
    chain_counts: dict[str, int] = field(default_factory=dict)
    adjacent_pair_counts: dict[str, int] = field(default_factory=dict)
    per_root_instance_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    per_root_document_counts: dict[str, dict[str, int]] = field(default_factory=dict)


def discover_svg_paths(inputs: Sequence[Path | str] | None = None) -> list[Path]:
    """Discover SVG and SVGZ files under the provided inputs."""

    candidates = inputs or DEFAULT_INPUTS
    found: set[Path] = set()
    for candidate in candidates:
        path = Path(candidate)
        if not path.exists():
            continue
        if path.is_file():
            if path.suffix.lower() in SVG_SUFFIXES:
                found.add(path.resolve())
            continue
        for file_path in path.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in SVG_SUFFIXES:
                found.add(file_path.resolve())
    return sorted(found)


def analyze_filter_usage(
    svg_paths: Sequence[Path | str],
    *,
    roots: Sequence[Path | str] | None = None,
) -> FilterUsageReport:
    """Count filter primitive usage and common chains across SVG files."""

    normalized_paths = [Path(path).resolve() for path in svg_paths]
    normalized_roots = [Path(root).resolve() for root in (roots or DEFAULT_INPUTS)]

    primitive_instance_counts: Counter[str] = Counter()
    primitive_document_counts: Counter[str] = Counter()
    chain_counts: Counter[str] = Counter()
    adjacent_pair_counts: Counter[str] = Counter()
    per_root_instance_counts: dict[str, Counter[str]] = {
        _root_label(root): Counter() for root in normalized_roots
    }
    per_root_document_counts: dict[str, Counter[str]] = {
        _root_label(root): Counter() for root in normalized_roots
    }

    filtered_svgs = 0
    total_filter_elements = 0
    total_primitive_instances = 0

    for svg_path in normalized_paths:
        root_label = _classify_path(svg_path, normalized_roots)
        root_instance_counter = per_root_instance_counts.setdefault(root_label, Counter())
        root_document_counter = per_root_document_counts.setdefault(root_label, Counter())

        primitive_tags_by_doc: set[str] = set()
        filter_chains = _extract_filter_primitive_chains(svg_path)
        if not filter_chains:
            continue

        filtered_svgs += 1
        total_filter_elements += len(filter_chains)

        for chain in filter_chains:
            total_primitive_instances += len(chain)
            primitive_tags_by_doc.update(chain)
            primitive_instance_counts.update(chain)
            root_instance_counter.update(chain)
            if chain:
                chain_counts[" > ".join(chain)] += 1
            for left, right in zip(chain, chain[1:], strict=False):
                adjacent_pair_counts[f"{left} -> {right}"] += 1

        primitive_document_counts.update(primitive_tags_by_doc)
        root_document_counter.update(primitive_tags_by_doc)

    return FilterUsageReport(
        roots=[_root_label(root) for root in normalized_roots],
        total_svgs=len(normalized_paths),
        filtered_svgs=filtered_svgs,
        total_filter_elements=total_filter_elements,
        total_primitive_instances=total_primitive_instances,
        primitive_instance_counts=dict(primitive_instance_counts),
        primitive_document_counts=dict(primitive_document_counts),
        chain_counts=dict(chain_counts),
        adjacent_pair_counts=dict(adjacent_pair_counts),
        per_root_instance_counts={
            key: dict(counter) for key, counter in per_root_instance_counts.items()
        },
        per_root_document_counts={
            key: dict(counter) for key, counter in per_root_document_counts.items()
        },
    )


def render_markdown(report: FilterUsageReport, *, top_n: int = 15) -> str:
    """Render a compact Markdown summary."""

    lines = [
        "# Filter Usage Summary",
        "",
        f"- Roots: {', '.join(report.roots)}",
        f"- SVGs scanned: {report.total_svgs}",
        f"- SVGs with filter primitives: {report.filtered_svgs}",
        f"- Filter elements: {report.total_filter_elements}",
        f"- Primitive instances: {report.total_primitive_instances}",
        "",
        "## Top Primitives",
        "",
        "| Primitive | SVGs | Instances |",
        "| --- | ---: | ---: |",
    ]
    for primitive, instances in _sorted_counter(report.primitive_instance_counts, top_n):
        lines.append(
            f"| `{primitive}` | {report.primitive_document_counts.get(primitive, 0)} | {instances} |"
        )

    lines.extend(
        [
            "",
            "## Top Filter Chains",
            "",
            "| Chain | Count |",
            "| --- | ---: |",
        ]
    )
    for chain, count in _sorted_counter(report.chain_counts, top_n):
        lines.append(f"| `{chain}` | {count} |")

    lines.extend(
        [
            "",
            "## Top Adjacent Primitive Pairs",
            "",
            "| Pair | Count |",
            "| --- | ---: |",
        ]
    )
    for pair, count in _sorted_counter(report.adjacent_pair_counts, top_n):
        lines.append(f"| `{pair}` | {count} |")

    lines.extend(["", "## Per Root Top Primitives", ""])
    for root_name in sorted(report.per_root_instance_counts):
        lines.append(f"### `{root_name}`")
        lines.append("")
        lines.append("| Primitive | SVGs | Instances |")
        lines.append("| --- | ---: | ---: |")
        root_instances = report.per_root_instance_counts.get(root_name, {})
        root_docs = report.per_root_document_counts.get(root_name, {})
        for primitive, instances in _sorted_counter(root_instances, min(top_n, 10)):
            lines.append(
                f"| `{primitive}` | {root_docs.get(primitive, 0)} | {instances} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_report(
    report: FilterUsageReport,
    *,
    output_dir: Path,
    top_n: int = 15,
) -> tuple[Path, Path]:
    """Write JSON and Markdown reports under *output_dir*."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "filter_usage.json"
    markdown_path = output_dir / "summary.md"
    json_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(report, top_n=top_n), encoding="utf-8")
    return json_path, markdown_path


def _extract_filter_primitive_chains(svg_path: Path) -> list[list[str]]:
    try:
        xml_text = _read_svg_text(svg_path)
        root = etree.fromstring(xml_text.encode("utf-8"))
    except Exception:
        return []

    chains: list[list[str]] = []
    for filter_elem in root.xpath(".//*[local-name()='filter']"):
        if not isinstance(filter_elem, etree._Element):
            continue
        chain = [
            _local_name(child.tag)
            for child in filter_elem
            if isinstance(child.tag, str) and _local_name(child.tag).startswith("fe")
        ]
        if chain:
            chains.append(chain)
    return chains


def _read_svg_text(svg_path: Path) -> str:
    if svg_path.suffix.lower() == ".svgz":
        with gzip.open(svg_path, "rt", encoding="utf-8") as handle:
            return handle.read()
    return svg_path.read_text(encoding="utf-8")


def _classify_path(path: Path, roots: Sequence[Path]) -> str:
    for root in roots:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        return _root_label(root)
    return path.parent.as_posix()


def _root_label(root: Path) -> str:
    return root.as_posix()


def _local_name(tag: str) -> str:
    local = tag.split("}", 1)[-1] if "}" in tag else tag
    return local.strip().lower()


def _sorted_counter(counter: dict[str, int], top_n: int) -> Iterable[tuple[str, int]]:
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:top_n]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs",
        nargs="*",
        help="SVG roots or files to scan. Defaults to curated local corpora.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to write JSON and Markdown summaries.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=15,
        help="How many top rows to include per summary section.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    inputs = [Path(item) for item in args.inputs] if args.inputs else list(DEFAULT_INPUTS)
    svg_paths = discover_svg_paths(inputs)
    report = analyze_filter_usage(svg_paths, roots=inputs)
    if args.output_dir is not None:
        json_path, markdown_path = write_report(
            report,
            output_dir=args.output_dir,
            top_n=args.top,
        )
        print(json_path)
        print(markdown_path)
    else:
        print(render_markdown(report, top_n=args.top), end="")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
