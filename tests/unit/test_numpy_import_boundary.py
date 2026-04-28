from __future__ import annotations

import re
from pathlib import Path

_DIRECT_NUMPY_IMPORT = re.compile(
    r"^\s*(?:import\s+numpy\b|from\s+numpy\b)",
    re.MULTILINE,
)
_ALLOWED = {"src/svg2ooxml/common/numpy_compat.py"}


def test_numpy_imports_are_centralized() -> None:
    root = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    for path in (root / "src" / "svg2ooxml").rglob("*.py"):
        relative = str(path.relative_to(root))
        if relative in _ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        if _DIRECT_NUMPY_IMPORT.search(text):
            offenders.append(relative)

    assert not offenders, "direct NumPy imports must use common.numpy_compat: " + ", ".join(
        sorted(offenders)
    )
