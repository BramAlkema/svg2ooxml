"""Picture rendering helper tests."""

from __future__ import annotations

from svg2ooxml.drawingml.image import render_picture
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.scene import Image


def test_render_picture_serializes_blip_color_transforms_from_metadata() -> None:
    image = Image(
        origin=Point(10, 20),
        size=Rect(0, 0, 40, 30),
        data=b"\x89PNG\r\n\x1a\nstub",
        format="png",
        metadata={
            "blip_color_transforms": [
                {"tag": "satMod", "val": 55000},
                {"tag": "hueOff", "val": 8100000},
                {"tag": "alphaModFix", "amt": 55000},
            ]
        },
    )

    xml = render_picture(
        image,
        7,
        template='<a:blip r:embed="{R_ID}">{BLIP_EXTENSIONS_XML}</a:blip>',
        policy_for=lambda *_args, **_kwargs: {},
        register_media=lambda _image: "rId7",
    )

    assert xml is not None
    assert '<a:satMod val="55000"/>' in xml
    assert '<a:hueOff val="8100000"/>' in xml
    assert '<a:alphaModFix amt="55000"/>' in xml
