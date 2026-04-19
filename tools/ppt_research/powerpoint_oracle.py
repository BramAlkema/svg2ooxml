#!/usr/bin/env python3
"""Compatibility bridge to ``openxml_audit.pptx.oracle``."""

from __future__ import annotations

from typing import Any

from tools.ppt_research._openxml_audit_bridge import load_openxml_audit_module

_TARGET = None


def _target():
    global _TARGET
    if _TARGET is None:
        _TARGET = load_openxml_audit_module("openxml_audit.pptx.oracle")
    return _TARGET


def __getattr__(name: str) -> Any:
    return getattr(_target(), name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_target())))


def main() -> int:
    return int(_target().main())


if __name__ == "__main__":
    raise SystemExit(main())
