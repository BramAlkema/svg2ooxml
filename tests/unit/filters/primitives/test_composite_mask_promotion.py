"""Tests for feComposite mask promotion heuristics."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.primitives.composite import CompositeFilter
from svg2ooxml.telemetry import RenderTracer


class TestCompositeSimpleMaskDetection:
    """Test simple mask detection heuristic."""

    def test_detects_simple_mask_with_source_alpha(self):
        """Test that 'in' operator with SourceAlpha is detected as simple mask."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feComposite operator="in" in="SourceGraphic" in2="SourceAlpha"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
        )

        composite_filter = CompositeFilter()
        result = composite_filter.apply(composite_elem, context)

        # Should detect as simple mask
        assert result.metadata["is_simple_mask"] is True

        # Telemetry should record simple mask
        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        assert decisions[0].metadata["is_simple_mask"] is True
        assert "simple mask" in decisions[0].reason

    def test_detects_simple_mask_with_valid_mask_input(self):
        """Test that mask with drawable content is detected as simple."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feFlood result="mask" flood-color="#FF0000"/>
                <feComposite operator="in" in="SourceGraphic" in2="mask"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        # Create pipeline state with mask result
        pipeline_state = {
            "mask": FilterResult(
                success=True,
                drawingml="<a:effectLst><mock/></a:effectLst>",
                metadata={"flood_color": "FF0000"},
            )
        }

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
            pipeline_state=pipeline_state,
        )

        composite_filter = CompositeFilter()
        result = composite_filter.apply(composite_elem, context)

        # Should detect as simple mask
        assert result.metadata["is_simple_mask"] is True

    def test_out_operator_detected_as_simple_mask(self):
        """Test that 'out' operator is detected as simple mask."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feComposite operator="out" in="SourceGraphic" in2="SourceAlpha"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
        )

        composite_filter = CompositeFilter()
        result = composite_filter.apply(composite_elem, context)

        # Should detect as simple mask
        assert result.metadata["is_simple_mask"] is True

    def test_atop_operator_detected_as_simple_mask(self):
        """Test that 'atop' operator is detected as simple mask."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feComposite operator="atop" in="SourceGraphic" in2="SourceAlpha"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
        )

        composite_filter = CompositeFilter()
        result = composite_filter.apply(composite_elem, context)

        # Should detect as simple mask
        assert result.metadata["is_simple_mask"] is True

    def test_xor_operator_detected_as_simple_mask(self):
        """Test that 'xor' operator is detected as simple mask."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feComposite operator="xor" in="SourceGraphic" in2="SourceAlpha"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
        )

        composite_filter = CompositeFilter()
        result = composite_filter.apply(composite_elem, context)

        # Should detect as simple mask
        assert result.metadata["is_simple_mask"] is True

    def test_arithmetic_operator_not_simple_mask(self):
        """Test that arithmetic operator is NOT detected as simple mask."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feComposite operator="arithmetic" k1="0.5" k2="0.5" k3="0" k4="0"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
        )

        composite_filter = CompositeFilter()
        result = composite_filter.apply(composite_elem, context)

        # Arithmetic should NOT be simple mask
        # (Note: result won't have is_simple_mask key because arithmetic path doesn't call _is_simple_mask)
        assert result.metadata.get("is_simple_mask") is None

    def test_over_operator_not_simple_mask(self):
        """Test that 'over' operator is NOT detected as simple mask."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feComposite operator="over" in="SourceGraphic" in2="SourceAlpha"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
        )

        composite_filter = CompositeFilter()
        result = composite_filter.apply(composite_elem, context)

        # 'over' operator doesn't go through masking path, so no is_simple_mask key
        assert result.metadata.get("is_simple_mask") is None


class TestCompositeAlphaCompositing:
    """Test that simple masks produce native DrawingML output."""

    def test_simple_mask_produces_native_drawingml(self):
        """Test that simple mask case produces native DrawingML (not EMF)."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feFlood result="mask" flood-color="#FF0000"/>
                <feComposite operator="in" in="SourceGraphic" in2="mask"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        # Create pipeline state with mask
        pipeline_state = {
            "mask": FilterResult(
                success=True,
                drawingml='<a:effectLst><a:glow rad="50000"><a:srgbClr val="FF0000"/></a:glow></a:effectLst>',
                metadata={"flood_color": "FF0000"},
            )
        }

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
            pipeline_state=pipeline_state,
        )

        composite_filter = CompositeFilter()
        result = composite_filter.apply(composite_elem, context)

        # Should produce DrawingML (native rendering)
        assert result.drawingml is not None
        assert result.drawingml != ""
        assert result.fallback is None  # No EMF fallback needed
        assert result.metadata["native_support"] is True

        # Telemetry should record native strategy
        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        assert decisions[0].strategy == "native"
        assert decisions[0].metadata["is_simple_mask"] is True

    def test_simple_mask_without_content_fallsback(self):
        """Test that mask without content falls back to EMF."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feComposite operator="in" in="SourceGraphic" in2="empty"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        # Pipeline state with empty mask
        pipeline_state = {
            "empty": FilterResult(
                success=True,
                drawingml="",  # Empty content
                metadata={},
            )
        }

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
            pipeline_state=pipeline_state,
        )

        composite_filter = CompositeFilter()
        result = composite_filter.apply(composite_elem, context)

        # Should fall back to EMF
        assert result.drawingml == ""
        assert result.fallback == "emf"
        assert result.metadata["native_support"] is False

        # Telemetry should record EMF fallback
        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        assert decisions[0].strategy == "emf"
        assert decisions[0].metadata["fallback_reason"] == "mask_empty"


class TestCompositeDegenerateMasks:
    """Test handling of degenerate mask cases that should fall back."""

    def test_mask_with_non_native_support_not_simple(self):
        """Test that mask with native_support=False is NOT detected as simple."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feComposite operator="in" in="SourceGraphic" in2="fallback_mask"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        # Mask that fell back to EMF (e.g., from unsupported filter primitive)
        pipeline_state = {
            "fallback_mask": FilterResult(
                success=True,
                drawingml="<emf-placeholder/>",  # EMF placeholder, not proper DrawingML
                metadata={"native_support": False, "fallback_reason": "unsupported_filter"},
            )
        }

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
            pipeline_state=pipeline_state,
        )

        composite_filter = CompositeFilter()
        result = composite_filter.apply(composite_elem, context)

        # Should NOT be detected as simple mask (mask isn't native)
        assert result.metadata["is_simple_mask"] is False

        # Should fall back to EMF
        assert result.drawingml == ""
        assert result.fallback == "emf"
        assert result.metadata["native_support"] is False

        # Telemetry should record complex mask fallback
        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        assert decisions[0].strategy == "emf"
        assert decisions[0].metadata["is_simple_mask"] is False
        assert "complex mask → fallback" in decisions[0].reason

    def test_mask_with_invalid_drawingml_not_simple(self):
        """Test that mask with invalid DrawingML structure is NOT simple."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feComposite operator="in" in="SourceGraphic" in2="invalid_mask"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        # Mask with invalid DrawingML (doesn't start with <a:effectLst>)
        pipeline_state = {
            "invalid_mask": FilterResult(
                success=True,
                drawingml="<invalid><content/></invalid>",
                metadata={"native_support": True},  # Claims native but structure is wrong
            )
        }

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
            pipeline_state=pipeline_state,
        )

        composite_filter = CompositeFilter()
        result = composite_filter.apply(composite_elem, context)

        # Should NOT be detected as simple mask (invalid structure)
        assert result.metadata["is_simple_mask"] is False

        # Should fall back to EMF because _combine_masking won't find valid effects
        assert result.drawingml == ""
        assert result.fallback == "emf"
        assert result.metadata["native_support"] is False

    def test_mask_without_effect_list_fallsback(self):
        """Test that mask without <a:effectLst> structure falls back cleanly."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feComposite operator="in" in="SourceGraphic" in2="plain_mask"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        # Mask with plain text content (no effect list structure)
        pipeline_state = {
            "plain_mask": FilterResult(
                success=True,
                drawingml="some plain content",
                metadata={},
            )
        }

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
            pipeline_state=pipeline_state,
        )

        composite_filter = CompositeFilter()
        result = composite_filter.apply(composite_elem, context)

        # Should NOT be simple (doesn't start with <a:effectLst>)
        assert result.metadata["is_simple_mask"] is False

        # Should produce empty drawingml (no valid effects to extract)
        assert result.drawingml == ""
        assert result.fallback == "emf"
        assert result.metadata["native_support"] is False
        assert result.metadata["fallback_reason"] == "mask_missing_effects"

    def test_prevents_empty_effect_list_emission(self):
        """Guard against accidentally emitting <a:effectLst></a:effectLst>."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feComposite operator="in" in="SourceGraphic" in2="degenerate"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        # Mask with empty effect list (valid structure but no content)
        pipeline_state = {
            "degenerate": FilterResult(
                success=True,
                drawingml="<a:effectLst></a:effectLst>",
                metadata={},
            )
        }

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
            pipeline_state=pipeline_state,
        )

        composite_filter = CompositeFilter()
        result = composite_filter.apply(composite_elem, context)

        # Should detect this but _combine_masking should catch empty effects
        # The heuristic will pass (starts with <a:effectLst>)
        assert result.metadata["is_simple_mask"] is True

        # But _combine_masking should return empty drawingml
        # (extract_effect_children will return empty string for empty list)
        assert result.drawingml == ""
        assert result.fallback == "emf"
        assert result.metadata["fallback_reason"] == "mask_missing_effects"
