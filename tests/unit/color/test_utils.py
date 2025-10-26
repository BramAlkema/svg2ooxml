from svg2ooxml.color import color_to_hex


def test_color_to_hex_handles_named() -> None:
    assert color_to_hex("red") == "FF0000"


def test_color_to_hex_handles_hex() -> None:
    assert color_to_hex("#abc") == "AABBCC"
    assert color_to_hex("#112233") == "112233"


def test_color_to_hex_handles_rgb() -> None:
    assert color_to_hex("rgb(0, 128, 255)") == "0080FF"


def test_color_to_hex_handles_invalid() -> None:
    assert color_to_hex("invalid", default="123456") == "123456"
