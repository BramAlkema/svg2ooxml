"""Integration tests for filter telemetry."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.filters.base import FilterContext
from svg2ooxml.filters.primitives.blend import BlendFilter
from svg2ooxml.filters.primitives.composite import CompositeFilter
from svg2ooxml.telemetry import RenderTracer


class TestBlendFilterTelemetry:
    """Test telemetry recording in BlendFilter."""

    def test_blend_multiply_records_native_decision(self):
        """Test that supported blend mode records native strategy."""
        from svg2ooxml.filters.base import FilterResult

        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feFlood flood-color="#FF0000" result="color"/>
                <feBlend mode="multiply" in="SourceGraphic" in2="color"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        blend_elem = root.find(".//{http://www.w3.org/2000/svg}feBlend")

        # Create pipeline state with flood color result
        pipeline_state = {
            "color": FilterResult(
                success=True,
                drawingml="<mock>",
                metadata={"flood_color": "FF0000", "flood_opacity": 1.0},
            )
        }

        # Create context with tracer and pipeline state
        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
            pipeline_state=pipeline_state,
        )

        # Apply blend filter
        blend_filter = BlendFilter()
        result = blend_filter.apply(blend_elem, context)

        # Verify telemetry was recorded
        decisions = tracer.get_decisions()
        assert len(decisions) == 1

        decision = decisions[0]
        assert decision.element_type == "feBlend"
        assert decision.strategy == "native"
        assert "multiply" in decision.reason
        assert decision.metadata["mode"] == "multiply"

    def test_blend_unsupported_mode_records_emf_decision(self):
        """Test that unsupported blend mode falls back to normal and can record EMF."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feBlend mode="color-dodge" in="SourceGraphic" in2="SourceAlpha"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        blend_elem = root.find(".//{http://www.w3.org/2000/svg}feBlend")

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
        )

        blend_filter = BlendFilter()
        result = blend_filter.apply(blend_elem, context)

        # Verify decision was recorded (normalized to "normal" by parser)
        decisions = tracer.get_decisions()
        assert len(decisions) == 1

        decision = decisions[0]
        assert decision.element_type == "feBlend"
        # Unsupported modes are normalized to "normal" by the parser
        assert decision.metadata["mode"] == "normal"

    def test_blend_without_tracer_still_works(self):
        """Test that filters work without tracer (telemetry disabled)."""
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feBlend mode="multiply" in="SourceGraphic" in2="SourceAlpha"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        blend_elem = root.find(".//{http://www.w3.org/2000/svg}feBlend")

        # Context without tracer
        context = FilterContext(filter_element=filter_elem)

        blend_filter = BlendFilter()
        result = blend_filter.apply(blend_elem, context)

        # Should succeed without errors
        assert result.success


class TestCompositeFilterTelemetry:
    """Test telemetry recording in CompositeFilter."""

    def test_composite_over_records_decision(self):
        """Test that 'over' operator records telemetry."""
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

        # Verify telemetry recorded
        decisions = tracer.get_decisions()
        assert len(decisions) == 1

        decision = decisions[0]
        assert decision.element_type == "feComposite"
        assert decision.metadata["operator"] == "over"

    def test_composite_masking_records_decision(self):
        """Test that masking operators record telemetry."""
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

        # Verify telemetry recorded
        decisions = tracer.get_decisions()
        assert len(decisions) == 1

        decision = decisions[0]
        assert decision.element_type == "feComposite"
        assert decision.metadata["operator"] == "in"
        assert "Masking" in decision.reason

    def test_composite_arithmetic_records_emf_fallback(self):
        """Test that arithmetic operator records EMF fallback."""
        tracer = RenderTracer()
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feComposite operator="arithmetic" k1="0.5" k2="0.5" k3="0" k4="0"
                             in="SourceGraphic" in2="SourceAlpha"/>
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

        # Verify EMF fallback recorded
        decisions = tracer.get_decisions()
        assert len(decisions) == 1

        decision = decisions[0]
        assert decision.element_type == "feComposite"
        assert decision.strategy == "emf"
        assert decision.metadata["operator"] == "arithmetic"


class TestTelemetryStatistics:
    """Test telemetry statistics aggregation."""

    def test_multiple_filters_aggregate_statistics(self):
        """Test that multiple filter decisions aggregate correctly."""
        from svg2ooxml.filters.base import FilterResult

        tracer = RenderTracer()

        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feBlend mode="multiply"/>
                <feComposite operator="arithmetic"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        blend_elem = root.find(".//{http://www.w3.org/2000/svg}feBlend")
        composite_elem = root.find(".//{http://www.w3.org/2000/svg}feComposite")

        # Create pipeline state with flood color for blend
        pipeline_state = {
            "SourceGraphic": FilterResult(
                success=True,
                drawingml="<mock>",
                metadata={"flood_color": "FF0000", "flood_opacity": 1.0},
            )
        }

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
            pipeline_state=pipeline_state,
        )

        # Process filters
        blend_filter = BlendFilter()
        composite_filter = CompositeFilter()

        blend_filter.apply(blend_elem, context)
        composite_filter.apply(composite_elem, context)

        # Check statistics
        json_output = tracer.to_json()
        import json
        data = json.loads(json_output)

        summary = data["summary"]
        assert summary["total_decisions"] == 2
        # multiply should be native, arithmetic should be emf
        assert summary["native_count"] == 1
        assert summary["emf_count"] == 1

    def test_telemetry_json_export_valid(self):
        """Test that telemetry exports valid JSON."""
        tracer = RenderTracer()

        svg = """<svg xmlns="http://www.w3.org/2000/svg">
            <filter id="f1">
                <feBlend mode="multiply"/>
            </filter>
        </svg>"""

        root = etree.fromstring(svg.encode())
        filter_elem = root.find(".//{http://www.w3.org/2000/svg}filter")
        blend_elem = root.find(".//{http://www.w3.org/2000/svg}feBlend")

        context = FilterContext(
            filter_element=filter_elem,
            tracer=tracer,
        )

        blend_filter = BlendFilter()
        blend_filter.apply(blend_elem, context)

        # Export and parse JSON
        json_str = tracer.to_json()
        import json
        data = json.loads(json_str)

        assert "decisions" in data
        assert "summary" in data
        assert len(data["decisions"]) == 1
        assert data["decisions"][0]["element_type"] == "feBlend"
