"""Ensure the public map mapper shim forwards to core implementations."""

from __future__ import annotations

import inspect

from svg2ooxml.core.pipeline.mappers import Mapper as CoreMapper
from svg2ooxml.core.pipeline.mappers.base import OutputFormat as CoreOutputFormat
from svg2ooxml.core.pipeline.mappers.clip_render import clip_result_to_xml as core_clip_result_to_xml
from svg2ooxml.core.pipeline.mappers.image_adapter import (
    ImageProcessingAdapter as CoreImageProcessingAdapter,
)
from svg2ooxml.core.pipeline.mappers.path_mapper import PathMapper as CorePathMapper
from svg2ooxml.core.pipeline.mappers.text_mapper import TextMapper as CoreTextMapper
from svg2ooxml.core.traversal.clip_geometry import (
    ClipComputeResult as CoreClipComputeResult,
    compute_clip_geometry as core_compute_clip_geometry,
)
from svg2ooxml.map.mapper import (
    ClipComputeResult,
    Mapper,
    OutputFormat,
    PathMapper,
    TextMapper,
    clip_result_to_xml,
    compute_clip_geometry,
    create_image_adapter,
)


def test_mapper_aliases_point_to_core_classes() -> None:
    assert Mapper is CoreMapper
    assert PathMapper is CorePathMapper
    assert TextMapper is CoreTextMapper
    assert OutputFormat is CoreOutputFormat


def test_clip_geometry_aliases() -> None:
    assert ClipComputeResult is CoreClipComputeResult
    assert compute_clip_geometry is core_compute_clip_geometry


def test_helper_functions_forward() -> None:
    assert clip_result_to_xml is core_clip_result_to_xml
    adapter_factory = create_image_adapter
    core_factory = CoreImageProcessingAdapter
    assert inspect.isclass(core_factory)
    adapter = adapter_factory(None)
    assert isinstance(adapter, core_factory)
