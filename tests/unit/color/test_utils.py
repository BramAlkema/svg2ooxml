from types import SimpleNamespace

from svg2ooxml.color import color_to_hex
from svg2ooxml.color.utils import rgb_channels_to_hex, rgb_object_to_hex


def test_color_to_hex_handles_named() -> None:
    assert color_to_hex("red") == "FF0000"


def test_color_to_hex_handles_hex() -> None:
    assert color_to_hex("#abc") == "AABBCC"
    assert color_to_hex("#112233") == "112233"


def test_color_to_hex_handles_rgb() -> None:
    assert color_to_hex("rgb(0, 128, 255)") == "0080FF"


def test_color_to_hex_handles_invalid() -> None:
    assert color_to_hex("invalid", default="123456") == "123456"


def test_rgb_object_to_hex_handles_unit_channels() -> None:
    color = SimpleNamespace(r=1.0, g=0.5, b=0.0)

    assert rgb_object_to_hex(color, scale="unit") == "FF8000"


def test_rgb_object_to_hex_handles_byte_channels() -> None:
    color = SimpleNamespace(r=255, g=128, b=0)

    assert rgb_object_to_hex(color, scale="byte") == "FF8000"


def test_rgb_channels_to_hex_handles_byte_and_unit_channels() -> None:
    assert rgb_channels_to_hex(255.9, 0.1, 0.5) == "FF0000"
    assert rgb_channels_to_hex(1.0, 0.5, 0.0, scale="unit", prefix="#") == "#FF8000"


def test_rgb_object_to_hex_can_return_prefixed_or_none_default() -> None:
    assert rgb_object_to_hex(SimpleNamespace(r=1, g=0, b=0), prefix="#") == "#FF0000"
    assert rgb_object_to_hex(None, default=None) is None
