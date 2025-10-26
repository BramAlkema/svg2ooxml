"""Tests for the image mapper."""

from __future__ import annotations

from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.scene import ClipRef, Image
from svg2ooxml.map.mapper import ImageMapper, OutputFormat
from svg2ooxml.services import configure_services


def _create_image(**overrides) -> Image:
    defaults = dict(
        origin=Point(0, 0),
        size=Rect(0, 0, 120, 80),
        data=b"\x89PNG\r\n",
        format="png",
        href=None,
        clip=None,
        mask=None,
        opacity=1.0,
        transform=None,
        metadata={},
    )
    defaults.update(overrides)
    return Image(**defaults)


def test_image_mapper_generates_picture_xml() -> None:
    services = configure_services(include_defaults=False)
    mapper = ImageMapper(policy=None, services=services)
    image = _create_image()

    result = mapper.map(image)

    assert result.output_format == OutputFormat.NATIVE_DML
    assert "<p:pic>" in result.xml_content
    assert result.metadata["relationship_id"]
    assert result.media_files and result.media_files[0]["data"] == image.data


def test_image_mapper_includes_clip_metadata() -> None:
    services = configure_services(include_defaults=False)
    mapper = ImageMapper(policy=None, services=services)
    clip_ref = ClipRef(
        clip_id="clip-1",
        primitives=(
            {
                "type": "ellipse",
                "cx": 0.0,
                "cy": 0.0,
                "rx": 10.0,
                "ry": 5.0,
                "transform": (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
            },
        ),
    )
    image = _create_image(clip=clip_ref)

    result = mapper.map(image)

    assert result.metadata.get("clip") is not None
    assert "custGeom" in result.xml_content
