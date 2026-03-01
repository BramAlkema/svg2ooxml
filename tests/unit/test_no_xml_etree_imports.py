from __future__ import annotations

import re
from pathlib import Path

_PATTERN = re.compile(r"^\s*(from|import)\s+xml\.etree\b", re.MULTILINE)


def test_no_stdlib_xml_etree_imports() -> None:
    root = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    for top in ("src", "tests", "tools"):
        base = root / top
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if _PATTERN.search(text):
                offenders.append(str(path.relative_to(root)))
    assert not offenders, f"stdlib xml.etree imports are banned: {', '.join(sorted(offenders))}"
