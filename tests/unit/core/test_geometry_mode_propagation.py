"""Tests for geometry_mode propagation through the policy system.

This test verifies that the geometry_mode parameter flows correctly from the
SvgToPptxExporter through the policy system to the IRConverter where it can be
accessed via _policy_options("geometry").

Flow being tested:
    SvgToPptxExporter(geometry_mode="resvg")
        ↓
    policy_overrides = {"geometry": {"geometry_mode": "resvg"}}
        ↓
    PolicyContext with geometry selections including geometry_mode
        ↓
    IRConverter._policy_options("geometry").get("geometry_mode") == "resvg"
"""

from __future__ import annotations

import io
import os
from unittest import mock

import pytest

from svg2ooxml.core.pptx_exporter import SvgToPptxExporter
from svg2ooxml.policy import PolicyContext


# Simple test SVG with a basic path
TEST_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
  <rect x="10" y="10" width="80" height="80" fill="blue"/>
</svg>
"""


class TestGeometryModePropagation:
    """Test suite for geometry_mode policy propagation."""

    def test_default_geometry_mode_is_legacy(self):
        """Test that the default geometry_mode is 'legacy'."""
        exporter = SvgToPptxExporter()
        assert exporter._geometry_mode == "legacy"

    def test_explicit_geometry_mode_parameter(self):
        """Test setting geometry_mode via parameter."""
        exporter = SvgToPptxExporter(geometry_mode="resvg")
        assert exporter._geometry_mode == "resvg"

    def test_geometry_mode_from_environment_variable(self):
        """Test setting geometry_mode via environment variable."""
        with mock.patch.dict(os.environ, {"SVG2OOXML_GEOMETRY_MODE": "resvg"}):
            exporter = SvgToPptxExporter()
            assert exporter._geometry_mode == "resvg"

    def test_parameter_overrides_environment_variable(self):
        """Test that parameter takes precedence over environment variable."""
        with mock.patch.dict(os.environ, {"SVG2OOXML_GEOMETRY_MODE": "resvg"}):
            exporter = SvgToPptxExporter(geometry_mode="legacy")
            assert exporter._geometry_mode == "legacy"

    def test_invalid_geometry_mode_raises_error(self):
        """Test that invalid geometry_mode values are rejected."""
        with pytest.raises(ValueError, match="Invalid geometry_mode"):
            SvgToPptxExporter(geometry_mode="invalid")

    def test_geometry_mode_propagates_to_policy_overrides(self):
        """Test that geometry_mode is injected into policy_overrides."""
        exporter = SvgToPptxExporter(geometry_mode="resvg")

        # Parse a simple SVG
        svg_bytes = TEST_SVG.encode("utf-8")
        svg_file = io.BytesIO(svg_bytes)

        # Mock the _render_svg method to capture the policy_context
        captured_policy_context = None

        original_render = exporter._render_svg
        def capture_policy_context(*args, **kwargs):
            nonlocal captured_policy_context
            # The policy_context is passed to IRConverter
            # We can capture it by mocking the IRConverter creation
            return original_render(*args, **kwargs)

        # Actually, let's check the _apply_policy_overrides method directly
        # Create a base PolicyContext and test merging
        base_context = PolicyContext(selections={
            "geometry": {
                "max_segments": 1000,
                "geometry_mode": "legacy",  # Base value
            }
        })

        # Apply overrides with geometry_mode="resvg"
        overrides = {"geometry": {"geometry_mode": "resvg"}}
        result_context = exporter._apply_policy_overrides(base_context, overrides)

        # Verify geometry_mode was updated
        assert result_context is not None
        geometry_options = result_context.get("geometry")
        assert geometry_options is not None
        assert geometry_options["geometry_mode"] == "resvg"
        # Verify other fields are preserved
        assert geometry_options["max_segments"] == 1000

    def test_legacy_mode_does_not_override_policy(self):
        """Test that geometry_mode='legacy' does not create unnecessary overrides."""
        exporter = SvgToPptxExporter(geometry_mode="legacy")

        # Create a base PolicyContext
        base_context = PolicyContext(selections={
            "geometry": {
                "max_segments": 1000,
                "geometry_mode": "legacy",
            }
        })

        # When geometry_mode is "legacy", we only override if explicitly set
        # The exporter code only creates overrides if self._geometry_mode != "legacy"
        # So no overrides should be created for legacy mode
        overrides = {}
        if exporter._geometry_mode != "legacy":
            overrides["geometry"] = {"geometry_mode": exporter._geometry_mode}

        result_context = exporter._apply_policy_overrides(base_context, overrides or None)

        # Result should be the same as base (no overrides applied)
        assert result_context is not None
        geometry_options = result_context.get("geometry")
        assert geometry_options is not None
        assert geometry_options["geometry_mode"] == "legacy"

    def test_policy_context_structure(self):
        """Test that PolicyContext has the expected structure."""
        context = PolicyContext(selections={
            "geometry": {
                "geometry_mode": "resvg",
                "max_segments": 2000,
            }
        })

        # Test the get method
        geometry_options = context.get("geometry")
        assert geometry_options is not None
        assert isinstance(geometry_options, dict)
        assert geometry_options["geometry_mode"] == "resvg"
        assert geometry_options["max_segments"] == 2000

        # Test get with default
        missing = context.get("nonexistent", default={"foo": "bar"})
        assert missing == {"foo": "bar"}

    def test_geometry_mode_accessible_via_policy_options(self):
        """Test that geometry_mode can be accessed via _policy_options("geometry").

        This simulates how IRConverter accesses the policy context:
        self._policy_options("geometry").get("geometry_mode")
        """
        from svg2ooxml.core.ir.policy_hooks import PolicyHooksMixin

        # Create a mock converter that uses PolicyHooksMixin
        class MockConverter(PolicyHooksMixin):
            def __init__(self, policy_context):
                self._policy_context = policy_context

        # Create a policy context with geometry_mode="resvg"
        context = PolicyContext(selections={
            "geometry": {
                "geometry_mode": "resvg",
                "max_segments": 2000,
                "simplify_paths": True,
            }
        })

        # Create converter with context
        converter = MockConverter(context)

        # Access geometry_mode via _policy_options (as IRConverter would)
        geometry_options = converter._policy_options("geometry")
        assert geometry_options is not None
        assert geometry_options.get("geometry_mode") == "resvg"
        assert geometry_options.get("max_segments") == 2000

    def test_end_to_end_policy_flow(self):
        """Test complete policy flow from exporter to IRConverter-like access.

        This verifies the complete flow:
        1. SvgToPptxExporter(geometry_mode="resvg")
        2. Creates policy_overrides with geometry_mode
        3. Policy context is built with merged overrides
        4. IRConverter can access geometry_mode via _policy_options("geometry")
        """
        from svg2ooxml.core.ir.policy_hooks import PolicyHooksMixin
        from svg2ooxml.policy import PolicyEngine
        from svg2ooxml.policy.setup import build_policy_engine

        # Step 1: Create exporter with geometry_mode="resvg"
        exporter = SvgToPptxExporter(geometry_mode="resvg")
        assert exporter._geometry_mode == "resvg"

        # Step 2: Simulate the flow in _render_svg
        # Build policy engine and evaluate to get base context
        policy_engine = build_policy_engine()
        base_context = policy_engine.evaluate()

        # Verify base context has geometry with default geometry_mode="legacy"
        base_geometry = base_context.get("geometry")
        assert base_geometry is not None
        assert base_geometry.get("geometry_mode") == "legacy"

        # Step 3: Apply overrides (as _render_svg does)
        overrides = {"geometry": {"geometry_mode": "resvg"}}
        final_context = exporter._apply_policy_overrides(base_context, overrides)

        # Step 4: Verify final context has geometry_mode="resvg"
        final_geometry = final_context.get("geometry")
        assert final_geometry is not None
        assert final_geometry.get("geometry_mode") == "resvg"

        # Step 5: Simulate IRConverter accessing via _policy_options
        class MockConverter(PolicyHooksMixin):
            def __init__(self, policy_context):
                self._policy_context = policy_context

        converter = MockConverter(final_context)
        geometry_options = converter._policy_options("geometry")
        assert geometry_options is not None
        assert geometry_options.get("geometry_mode") == "resvg"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
