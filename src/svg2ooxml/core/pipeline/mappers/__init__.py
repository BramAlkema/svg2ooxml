"""Modern mapper implementations for svg2ooxml."""

from .base import Mapper, MapperError, MapperResult, OutputFormat, validate_mapper_result
from .clip_render import clip_result_to_xml
from .group_mapper import GroupMapper
from .image_adapter import ImageProcessingAdapter, ImageProcessingResult, create_image_adapter
from .image_mapper import ImageDecision, ImageMapper
from .path_mapper import PathDecision, PathMapper
from .text_mapper import TextMapper

__all__ = [
    "Mapper",
    "MapperError",
    "MapperResult",
    "OutputFormat",
    "validate_mapper_result",
    "clip_result_to_xml",
    "GroupMapper",
    "ImageProcessingAdapter",
    "ImageProcessingResult",
    "create_image_adapter",
    "ImageDecision",
    "ImageMapper",
    "PathDecision",
    "PathMapper",
    "TextMapper",
]
