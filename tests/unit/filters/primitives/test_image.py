from __future__ import annotations

import base64

from lxml import etree

from svg2ooxml.filters.base import FilterContext
from svg2ooxml.filters.primitives.image import ImageFilter


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAAWgmWQ0AAAAASUVORK5CYII="
)


def test_feimage_resolves_url_wrapped_href(tmp_path) -> None:
    image_path = tmp_path / "inline.png"
    image_path.write_bytes(PNG_1X1)

    primitive = etree.fromstring('<feImage href="url(\'inline.png\')"/>')
    context = FilterContext(
        filter_element=etree.Element("filter"),
        options={"base_dir": str(tmp_path)},
    )

    result = ImageFilter().apply(primitive, context)

    assert result.metadata.get("image_resolved") is True
    assets = result.metadata.get("fallback_assets")
    assert isinstance(assets, list) and assets
    assert assets[0].get("format") == "png"
