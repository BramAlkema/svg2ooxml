"""Ensure filter test policy switch honors legacy/modern modes."""

from __future__ import annotations

import importlib


def test_filter_policy_switch_legacy(monkeypatch) -> None:
    monkeypatch.setenv("SVG2OOXML_FILTER_POLICY", "legacy")
    monkeypatch.setenv("SVG2OOXML_FILTER_POLICY_STRICT", "1")

    import tests.unit.filters.policy as policy

    importlib.reload(policy)

    class Dummy:
        fallback = "emf"
        strategy = "vector"
        metadata = {}

    policy.assert_fallback(Dummy, modern="bitmap", legacy="emf")
    policy.assert_strategy(Dummy, modern="raster", legacy="vector")
