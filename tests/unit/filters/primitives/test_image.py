from __future__ import annotations

import base64
from types import SimpleNamespace

from lxml import etree

from svg2ooxml.filters.base import FilterContext
from svg2ooxml.filters.primitives.image import ImageFilter
from svg2ooxml.services.image_service import FileResolver, ImageService

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


def test_feimage_context_asset_root_blocks_service_file_bypass(tmp_path) -> None:
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    outside_path = tmp_path / "outside.png"
    outside_path.write_bytes(PNG_1X1)

    image_service = ImageService()
    image_service.register_resolver(
        FileResolver(tmp_path, asset_root=tmp_path),
        prepend=True,
    )
    primitive = etree.fromstring(f'<feImage href="{outside_path}"/>')
    context = FilterContext(
        filter_element=etree.Element("filter"),
        services=SimpleNamespace(image_service=image_service),
        options={
            "source_path": str(asset_root / "scene.svg"),
            "asset_root": str(asset_root),
        },
    )

    result = ImageFilter().apply(primitive, context)

    assert result.metadata.get("image_resolved") is False
    assert "fallback_assets" not in result.metadata
