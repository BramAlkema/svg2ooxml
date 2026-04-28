"""Tests for dependency-light filter policy runtime helpers."""

from __future__ import annotations

import importlib
import sys


def test_filter_policy_runtime_does_not_import_full_planner() -> None:
    sys.modules.pop("svg2ooxml.services.filter_policy_runtime", None)
    sys.modules.pop("svg2ooxml.filters.planner", None)

    importlib.import_module("svg2ooxml.services.filter_policy_runtime")

    assert "svg2ooxml.filters.planner" not in sys.modules
