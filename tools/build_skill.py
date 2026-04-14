#!/usr/bin/env python
"""Build the pptx-animation Claude skill from the svg2ooxml oracle.

Assembles a self-contained skill directory by:

1. Copying the hand-written SKILL.md from tools/skill_sources/
2. Copying the hand-written Python scripts from tools/skill_sources/scripts/
3. Copying the hand-written reference docs from tools/skill_sources/references_static/
4. Vendoring the oracle SSOT XML files from src/svg2ooxml/assets/animation_oracle/
5. Generating markdown reference docs (filter_vocabulary.md, attrname_vocabulary.md,
   dead_paths.md) from the SSOT XML files via the oracle's typed loaders

The output directory defaults to .claude/skills/pptx-animation/ so the
svg2ooxml repo itself picks up the skill when Claude runs inside it.
Pass --output to write to a different location (e.g. dist/ for a
standalone release tarball).

The same script is used for in-tree builds and standalone release builds.

Usage:

    python tools/build_skill.py
    python tools/build_skill.py --output dist/pptx-animation-skill
    python tools/build_skill.py --check  # verify tree is up to date (CI)
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from svg2ooxml.drawingml.animation.oracle import (
    AttrNameEntry,
    DeadPath,
    FilterEntry,
    default_oracle,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ORACLE_SRC = REPO_ROOT / "src" / "svg2ooxml" / "assets" / "animation_oracle"
SKILL_SOURCES = REPO_ROOT / "tools" / "skill_sources"
DEFAULT_OUTPUT = REPO_ROOT / ".claude" / "skills" / "pptx-animation"


def build(output_dir: Path) -> None:
    """Assemble the skill directory."""
    print(f"Building skill → {output_dir}")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    _copy_hand_written(output_dir)
    _vendor_oracle(output_dir)
    _generate_references(output_dir)
    _make_scripts_executable(output_dir)

    print(f"Done. Skill contents:")
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(output_dir)
            print(f"  {rel}")


def _copy_hand_written(output_dir: Path) -> None:
    """Copy SKILL.md, scripts/, and references_static/ (renamed to references/)."""
    # SKILL.md at the root.
    src_skill_md = SKILL_SOURCES / "SKILL.md"
    if not src_skill_md.is_file():
        raise FileNotFoundError(f"SKILL.md missing at {src_skill_md}")
    shutil.copy(src_skill_md, output_dir / "SKILL.md")

    # Scripts directory verbatim.
    src_scripts = SKILL_SOURCES / "scripts"
    if not src_scripts.is_dir():
        raise FileNotFoundError(f"scripts/ missing at {src_scripts}")
    shutil.copytree(src_scripts, output_dir / "scripts")

    # references_static → references (hand-written markdown docs).
    src_refs = SKILL_SOURCES / "references_static"
    dst_refs = output_dir / "references"
    dst_refs.mkdir(parents=True, exist_ok=True)
    if src_refs.is_dir():
        for src_file in src_refs.glob("*.md"):
            shutil.copy(src_file, dst_refs / src_file.name)


def _vendor_oracle(output_dir: Path) -> None:
    """Copy every SSOT file and slot template from the oracle directory."""
    oracle_out = output_dir / "oracle"
    oracle_out.mkdir(parents=True, exist_ok=True)

    # Copy every file in the oracle tree (SSOT xml + slot xml + index.json + README.md).
    for src_file in ORACLE_SRC.rglob("*"):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(ORACLE_SRC)
        dst = oracle_out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src_file, dst)


def _generate_references(output_dir: Path) -> None:
    """Render markdown reference files from the oracle's typed loaders."""
    refs = output_dir / "references"
    refs.mkdir(parents=True, exist_ok=True)

    oracle = default_oracle()

    (refs / "filter_vocabulary.md").write_text(
        _render_filter_vocabulary(oracle.filter_vocabulary()),
        encoding="utf-8",
    )
    (refs / "attrname_vocabulary.md").write_text(
        _render_attrname_vocabulary(oracle.attrname_vocabulary()),
        encoding="utf-8",
    )
    (refs / "dead_paths.md").write_text(
        _render_dead_paths(oracle.dead_paths()),
        encoding="utf-8",
    )


def _render_filter_vocabulary(vocab: tuple[FilterEntry, ...]) -> str:
    lines: list[str] = [
        "# Filter Vocabulary",
        "",
        "The complete set of `<p:animEffect filter=\"...\">` string values PowerPoint recognises.",
        "Auto-generated from `oracle/filter_vocabulary.xml` — do not hand-edit.",
        "",
        "Loaded programmatically via:",
        "",
        "```python",
        "from svg2ooxml.drawingml.animation.oracle import default_oracle",
        "oracle = default_oracle()",
        "vocab = oracle.filter_vocabulary()      # tuple[FilterEntry, ...]",
        "entry = oracle.filter_entry('wipe(down)')",
        "```",
        "",
        "## Entries",
        "",
        "| Filter | Entrance preset | Exit preset | Verification | Description |",
        "|---|---|---|---|---|",
    ]
    for e in vocab:
        ent = (
            f"{e.entrance_preset_id}/{e.entrance_preset_subtype}"
            if e.entrance_preset_id is not None and e.entrance_preset_id > 0
            else "—"
        )
        ext = (
            f"{e.exit_preset_id}/{e.exit_preset_subtype}"
            if e.exit_preset_id is not None and e.exit_preset_id > 0
            else "—"
        )
        lines.append(
            f"| `{e.value}` | {ent} | {ext} | {e.verification} | {e.description} |"
        )
    lines.append("")
    lines.append("## Verification legend")
    lines.append("")
    lines.append("- `visually-verified` — empirically confirmed playing in PowerPoint via the tune loop.")
    lines.append("- `derived-from-handler` — structurally equivalent to a verified entry (e.g. additional direction/spoke subparameters).")
    lines.append("")
    return "\n".join(lines)


def _render_attrname_vocabulary(vocab: tuple[AttrNameEntry, ...]) -> str:
    lines: list[str] = [
        "# attrName Vocabulary",
        "",
        "The 17 `<p:attrName>` values PowerPoint emits natively. Confirmed",
        "exhaustive by scanning 400+ authored animations across reference decks.",
        "Auto-generated from `oracle/attrname_vocabulary.xml` — do not hand-edit.",
        "",
        "Loaded programmatically via:",
        "",
        "```python",
        "from svg2ooxml.drawingml.animation.oracle import default_oracle",
        "oracle = default_oracle()",
        "vocab = oracle.attrname_vocabulary()    # tuple[AttrNameEntry, ...]",
        "entry = oracle.attrname_entry('fillcolor')",
        "oracle.is_valid_attrname('fill.opacity')  # False — see dead_paths.md",
        "```",
        "",
    ]
    by_category: dict[str, list[AttrNameEntry]] = {}
    for entry in vocab:
        by_category.setdefault(entry.category, []).append(entry)

    category_order = [
        "geometry", "rotation", "visibility", "color",
        "fill-primer", "stroke-primer",
        "text-formatting", "opacity",
    ]
    seen: set[str] = set()
    for cat in category_order + sorted(by_category):
        if cat in seen or cat not in by_category:
            continue
        seen.add(cat)
        lines.append(f"## {cat}")
        lines.append("")
        for e in by_category[cat]:
            lines.append(f"### `{e.value}`")
            lines.append("")
            lines.append(f"- **Scope:** {e.scope}")
            lines.append(f"- **Verification:** {e.verification}")
            lines.append(f"- **Used by:** {e.used_by}")
            lines.append("")
            lines.append(e.description)
            lines.append("")
    return "\n".join(lines)


def _render_dead_paths(dead_paths: tuple[DeadPath, ...]) -> str:
    lines: list[str] = [
        "# Dead Paths — Do Not Use",
        "",
        "XML shapes that PowerPoint's parser accepts but its playback engine",
        "silently drops at slideshow time. Every entry below has been",
        "empirically verified to fail via the tune loop.",
        "",
        "Auto-generated from `oracle/dead_paths.xml` — do not hand-edit.",
        "",
        "Loaded programmatically via:",
        "",
        "```python",
        "from svg2ooxml.drawingml.animation.oracle import default_oracle",
        "oracle = default_oracle()",
        "paths = oracle.dead_paths()        # tuple[DeadPath, ...]",
        "dp = oracle.dead_path('anim-fill-opacity')  # lookup by id",
        "```",
        "",
        "Use `scripts/validate.py` to check arbitrary XML against this catalog:",
        "",
        "```bash",
        "cat some_timing.xml | python scripts/validate.py",
        "```",
        "",
        "## Entries",
        "",
    ]
    for dp in dead_paths:
        lines.append(f"### `{dp.id}`")
        lines.append("")
        attrs = ", ".join(
            f"`{k}={v}`" for k, v in zip(dp.attribute_names, dp.attribute_values)
        )
        lines.append(f"**Shape:** `{dp.element}` with {attrs}")
        if dp.context:
            lines.append("")
            lines.append(f"**Context:** {dp.context}")
        lines.append("")
        lines.append(f"**Verdict:** `{dp.verdict}`")
        lines.append("")
        lines.append(f"**Source:** {dp.source}")
        lines.append("")
        lines.append(dp.description.strip())
        lines.append("")
        lines.append(f"**Replacement slot:** `{dp.replacement_slot}`")
        lines.append("")
        lines.append(f"{dp.replacement_note}")
        lines.append("")
    return "\n".join(lines)


def _make_scripts_executable(output_dir: Path) -> None:
    """Set +x on every .py in scripts/ so they can be invoked directly."""
    scripts_dir = output_dir / "scripts"
    if not scripts_dir.is_dir():
        return
    for script in scripts_dir.glob("*.py"):
        mode = script.stat().st_mode
        script.chmod(mode | 0o111)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output directory (default: {DEFAULT_OUTPUT.relative_to(REPO_ROOT)}).",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Build to a temp directory and compare to --output; exit non-zero if they differ.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_out = Path(tmp) / "pptx-animation"
            build(tmp_out)
            if not args.output.exists():
                print(
                    f"ERROR: --check requested but {args.output} does not exist",
                    file=sys.stderr,
                )
                return 2
            # Simple diff: iterate every file in tmp_out and compare to output.
            drift: list[str] = []
            for tmp_file in sorted(tmp_out.rglob("*")):
                if not tmp_file.is_file():
                    continue
                rel = tmp_file.relative_to(tmp_out)
                out_file = args.output / rel
                if not out_file.is_file():
                    drift.append(f"missing: {rel}")
                    continue
                if tmp_file.read_bytes() != out_file.read_bytes():
                    drift.append(f"changed: {rel}")
            for out_file in sorted(args.output.rglob("*")):
                if not out_file.is_file():
                    continue
                rel = out_file.relative_to(args.output)
                if not (tmp_out / rel).is_file():
                    drift.append(f"extra: {rel}")
            if drift:
                print(
                    "Skill drift detected (re-run tools/build_skill.py):",
                    file=sys.stderr,
                )
                for item in drift:
                    print(f"  {item}", file=sys.stderr)
                return 1
            print("Skill is up to date.")
            return 0
    build(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
