"""Smoke tests for the placeholder conversion pipeline."""

from svg2ooxml.core.pipeline import DEFAULT_STAGE_NAMES, ConversionPipeline


def test_pipeline_uses_default_stage_sequence() -> None:
    pipeline = ConversionPipeline()

    assert pipeline.stages == DEFAULT_STAGE_NAMES
    assert pipeline.describe_stage_names() == DEFAULT_STAGE_NAMES
