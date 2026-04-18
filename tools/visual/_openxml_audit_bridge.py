"""Helpers for bridging legacy svg2ooxml tool imports to openxml-audit."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


def load_openxml_audit_module(module_name: str) -> ModuleType:
    """Import an openxml-audit module, with a sibling-repo fallback for dev use."""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if not exc.name or (
            exc.name != "openxml_audit"
            and not exc.name.startswith("openxml_audit.")
        ):
            raise

    sibling_src = (
        Path(__file__).resolve().parents[3] / "openxml-audit" / "src"
    )
    if sibling_src.exists():
        sibling_src_str = str(sibling_src)
        if sibling_src_str not in sys.path:
            sys.path.insert(0, sibling_src_str)
        module_parts = module_name.split(".")
        for index in range(1, len(module_parts)):
            package_name = ".".join(module_parts[:index])
            package = sys.modules.get(package_name)
            if package is None or not hasattr(package, "__path__"):
                continue
            sibling_pkg = sibling_src.joinpath(*module_parts[:index])
            sibling_pkg_str = str(sibling_pkg)
            package_paths = list(package.__path__)
            if sibling_pkg_str not in package_paths:
                package.__path__.append(sibling_pkg_str)
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if not exc.name or (
                exc.name != "openxml_audit"
                and not exc.name.startswith("openxml_audit.")
            ):
                raise

    raise ModuleNotFoundError(
        "PowerPoint audit tooling moved to openxml-audit. "
        "Install `openxml-audit[pptx-lab]` or clone the sibling repository at "
        "`../openxml-audit`."
    )
