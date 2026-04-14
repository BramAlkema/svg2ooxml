"""Tests for tools/build_skill.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD_SCRIPT = REPO_ROOT / "tools" / "build_skill.py"
IN_TREE_SKILL = REPO_ROOT / ".claude" / "skills" / "pptx-animation"


@pytest.mark.unit
def test_build_skill_produces_expected_structure(tmp_path: Path) -> None:
    """build_skill.py assembles SKILL.md + scripts + references + oracle."""
    out = tmp_path / "built-skill"
    result = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), "--output", str(out)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"build_skill failed: {result.stderr}"

    # SKILL.md at root
    assert (out / "SKILL.md").is_file()
    skill_md = (out / "SKILL.md").read_text(encoding="utf-8")
    assert skill_md.startswith("---"), "SKILL.md missing frontmatter"
    assert "name: pptx-animation" in skill_md

    # Scripts
    scripts = out / "scripts"
    assert scripts.is_dir()
    for name in (
        "emit_compound.py",
        "emit_entrance.py",
        "emit_exit.py",
        "emit_motion.py",
        "validate.py",
        "query_vocabulary.py",
    ):
        assert (scripts / name).is_file(), f"missing script: {name}"

    # References
    refs = out / "references"
    assert refs.is_dir()
    for name in (
        "oracle_overview.md",
        "compound_api.md",
        "examples.md",
        "filter_vocabulary.md",     # auto-generated
        "attrname_vocabulary.md",   # auto-generated
        "dead_paths.md",            # auto-generated
    ):
        assert (refs / name).is_file(), f"missing reference: {name}"

    # Oracle vendored
    oracle = out / "oracle"
    assert oracle.is_dir()
    assert (oracle / "filter_vocabulary.xml").is_file()
    assert (oracle / "attrname_vocabulary.xml").is_file()
    assert (oracle / "dead_paths.xml").is_file()
    assert (oracle / "index.json").is_file()
    # Slot templates
    assert (oracle / "emph" / "compound.xml").is_file()
    assert (oracle / "emph" / "behaviors" / "rotate.xml").is_file()
    assert (oracle / "entr" / "filter_effect.xml").is_file()
    assert (oracle / "exit" / "filter_effect.xml").is_file()
    assert (oracle / "path" / "motion.xml").is_file()


@pytest.mark.unit
def test_generated_references_have_content(tmp_path: Path) -> None:
    """Auto-generated markdown references must contain core verified entries."""
    out = tmp_path / "built"
    subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), "--output", str(out)],
        cwd=REPO_ROOT,
        check=True,
    )

    filter_md = (out / "references" / "filter_vocabulary.md").read_text(encoding="utf-8")
    # At minimum the 16 verified filters must appear
    for f in ("fade", "dissolve", "wipe(down)", "circle(in)", "checkerboard(across)"):
        assert f"`{f}`" in filter_md, f"filter {f} missing from generated filter_vocabulary.md"

    attrname_md = (out / "references" / "attrname_vocabulary.md").read_text(encoding="utf-8")
    # All 17 valid attrNames must appear
    for a in (
        "ppt_x", "ppt_y", "ppt_w", "ppt_h", "r", "style.rotation",
        "style.visibility", "fillcolor", "fill.type", "fill.on",
        "stroke.color", "stroke.on", "style.color", "style.fontWeight",
        "style.textDecorationUnderline", "style.fontSize", "style.opacity",
    ):
        assert f"`{a}`" in attrname_md, f"attrName {a} missing"

    dead_md = (out / "references" / "dead_paths.md").read_text(encoding="utf-8")
    for dp_id in ("anim-fill-opacity", "anim-stroke-weight", "animeffect-image-isolated"):
        assert dp_id in dead_md


@pytest.mark.unit
def test_check_mode_passes_for_in_tree_skill() -> None:
    """--check mode should pass for the committed in-tree skill."""
    if not IN_TREE_SKILL.exists():
        pytest.skip("in-tree skill not yet built — run tools/build_skill.py first")
    result = subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--check",
            "--output",
            str(IN_TREE_SKILL),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"In-tree skill is out of date. Re-run tools/build_skill.py.\n"
        f"{result.stderr}"
    )
