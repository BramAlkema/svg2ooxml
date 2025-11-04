"""Unit tests for telemetry system."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from svg2ooxml.telemetry import RenderDecision, RenderTracer


class TestRenderDecision:
    """Tests for RenderDecision dataclass."""

    def test_create_decision(self):
        """Test creating a render decision."""
        timestamp = time.time()
        decision = RenderDecision(
            element_type="feBlend",
            strategy="native",
            reason="Supported blend mode: multiply",
            timestamp=timestamp,
            metadata={"mode": "multiply"},
        )

        assert decision.element_type == "feBlend"
        assert decision.strategy == "native"
        assert decision.reason == "Supported blend mode: multiply"
        assert decision.timestamp == timestamp
        assert decision.metadata == {"mode": "multiply"}

    def test_decision_to_dict(self):
        """Test converting decision to dictionary."""
        decision = RenderDecision(
            element_type="feComposite",
            strategy="emf",
            reason="Complex arithmetic operator",
            timestamp=1234567890.0,
            metadata={"operator": "arithmetic", "k1": 0.5},
        )

        result = decision.to_dict()

        assert result["element_type"] == "feComposite"
        assert result["strategy"] == "emf"
        assert result["reason"] == "Complex arithmetic operator"
        assert result["timestamp"] == 1234567890.0
        assert result["metadata"]["operator"] == "arithmetic"
        assert result["metadata"]["k1"] == 0.5

    def test_decision_without_metadata(self):
        """Test decision with default empty metadata."""
        decision = RenderDecision(
            element_type="path",
            strategy="native",
            reason="Simple path geometry",
            timestamp=time.time(),
        )

        assert decision.metadata == {}
        assert decision.to_dict()["metadata"] == {}


class TestRenderTracer:
    """Tests for RenderTracer class."""

    def test_create_tracer(self):
        """Test creating a tracer."""
        tracer = RenderTracer()
        assert tracer.get_decisions() == []

    def test_record_decision(self):
        """Test recording a single decision."""
        tracer = RenderTracer()

        tracer.record_decision(
            element_type="feBlend",
            strategy="native",
            reason="Supported mode",
        )

        decisions = tracer.get_decisions()
        assert len(decisions) == 1
        assert decisions[0].element_type == "feBlend"
        assert decisions[0].strategy == "native"
        assert decisions[0].reason == "Supported mode"

    def test_record_multiple_decisions(self):
        """Test recording multiple decisions."""
        tracer = RenderTracer()

        tracer.record_decision("feBlend", "native", "Multiply mode")
        tracer.record_decision("feComposite", "emf", "Arithmetic operator")
        tracer.record_decision("path", "native", "Simple geometry")

        decisions = tracer.get_decisions()
        assert len(decisions) == 3
        assert decisions[0].element_type == "feBlend"
        assert decisions[1].element_type == "feComposite"
        assert decisions[2].element_type == "path"

    def test_record_decision_with_metadata(self):
        """Test recording decision with metadata."""
        tracer = RenderTracer()

        tracer.record_decision(
            element_type="feBlend",
            strategy="native",
            reason="Supported mode",
            metadata={"mode": "screen", "input_count": 2},
        )

        decisions = tracer.get_decisions()
        assert decisions[0].metadata["mode"] == "screen"
        assert decisions[0].metadata["input_count"] == 2

    def test_clear_decisions(self):
        """Test clearing all decisions."""
        tracer = RenderTracer()

        tracer.record_decision("feBlend", "native", "Test")
        tracer.record_decision("feComposite", "emf", "Test")
        assert len(tracer.get_decisions()) == 2

        tracer.clear()
        assert len(tracer.get_decisions()) == 0

    def test_to_json(self):
        """Test JSON export."""
        tracer = RenderTracer()

        tracer.record_decision("feBlend", "native", "Multiply mode")
        tracer.record_decision("feComposite", "emf", "Arithmetic")

        json_str = tracer.to_json()
        data = json.loads(json_str)

        assert "decisions" in data
        assert "summary" in data
        assert len(data["decisions"]) == 2
        assert data["decisions"][0]["element_type"] == "feBlend"
        assert data["decisions"][1]["element_type"] == "feComposite"

    def test_to_json_empty_tracer(self):
        """Test JSON export with no decisions."""
        tracer = RenderTracer()
        json_str = tracer.to_json()
        data = json.loads(json_str)

        assert data["decisions"] == []
        assert data["summary"]["total_decisions"] == 0

    def test_to_file(self, tmp_path: Path):
        """Test writing to file."""
        tracer = RenderTracer()
        tracer.record_decision("feBlend", "native", "Test")

        output_file = tmp_path / "telemetry.json"
        tracer.to_file(output_file)

        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert len(data["decisions"]) == 1

    def test_to_file_creates_parent_directory(self):
        """Test that to_file creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracer = RenderTracer()
            tracer.record_decision("path", "native", "Test")

            output_file = Path(tmpdir) / "subdir" / "nested" / "telemetry.json"
            tracer.to_file(output_file)

            assert output_file.exists()
            assert output_file.parent.exists()

    def test_summary_statistics_all_native(self):
        """Test summary with all native decisions."""
        tracer = RenderTracer()

        for i in range(5):
            tracer.record_decision("path", "native", f"Test {i}")

        json_str = tracer.to_json()
        data = json.loads(json_str)
        summary = data["summary"]

        assert summary["total_decisions"] == 5
        assert summary["native_count"] == 5
        assert summary["emf_count"] == 0
        assert summary["raster_count"] == 0
        assert summary["native_rate"] == 1.0
        assert summary["emf_rate"] == 0.0
        assert summary["raster_rate"] == 0.0

    def test_summary_statistics_mixed_strategies(self):
        """Test summary with mixed strategies."""
        tracer = RenderTracer()

        tracer.record_decision("feBlend", "native", "Test 1")
        tracer.record_decision("feBlend", "native", "Test 2")
        tracer.record_decision("feComposite", "emf", "Test 3")
        tracer.record_decision("filter", "raster", "Test 4")

        json_str = tracer.to_json()
        data = json.loads(json_str)
        summary = data["summary"]

        assert summary["total_decisions"] == 4
        assert summary["native_count"] == 2
        assert summary["emf_count"] == 1
        assert summary["raster_count"] == 1
        assert summary["native_rate"] == 0.5
        assert summary["emf_rate"] == 0.25
        assert summary["raster_rate"] == 0.25

    def test_summary_empty_tracer(self):
        """Test summary with no decisions."""
        tracer = RenderTracer()
        json_str = tracer.to_json()
        data = json.loads(json_str)
        summary = data["summary"]

        assert summary["total_decisions"] == 0
        assert summary["native_count"] == 0
        assert summary["emf_count"] == 0
        assert summary["raster_count"] == 0
        assert summary["native_rate"] == 0.0
        assert summary["emf_rate"] == 0.0
        assert summary["raster_rate"] == 0.0

    def test_timestamp_recorded(self):
        """Test that timestamps are recorded correctly."""
        tracer = RenderTracer()

        before = time.time()
        tracer.record_decision("path", "native", "Test")
        after = time.time()

        decisions = tracer.get_decisions()
        timestamp = decisions[0].timestamp

        assert before <= timestamp <= after

    def test_decisions_are_independent_copies(self):
        """Test that get_decisions returns independent copies."""
        tracer = RenderTracer()
        tracer.record_decision("path", "native", "Test")

        decisions1 = tracer.get_decisions()
        decisions2 = tracer.get_decisions()

        assert decisions1 == decisions2
        assert decisions1 is not decisions2  # Different list objects
