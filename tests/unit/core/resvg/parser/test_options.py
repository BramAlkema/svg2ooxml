from __future__ import annotations

import base64

from svg2ooxml.core.resvg.parser.options import build_default_options

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def test_image_file_resolver_rejects_paths_outside_resources_dir(tmp_path) -> None:
    resources = tmp_path / "assets"
    resources.mkdir()
    inside = resources / "pixel.png"
    inside.write_bytes(PNG_1X1)
    outside = tmp_path / "secret.png"
    outside.write_bytes(PNG_1X1)

    resolver = build_default_options(resources_dir=resources).image_href_resolver

    assert resolver.resolve_file("pixel.png") == inside
    assert resolver.resolve_file("../secret.png") is None
    assert resolver.resolve_file(str(outside)) is None


def test_image_file_resolver_allows_parent_paths_inside_explicit_asset_root(
    tmp_path,
) -> None:
    resources = tmp_path / "fixtures" / "svg"
    resources.mkdir(parents=True)
    shared = tmp_path / "fixtures" / "images"
    shared.mkdir()
    image = shared / "pixel.png"
    image.write_bytes(PNG_1X1)
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG_1X1)

    resolver = build_default_options(
        resources_dir=resources,
        asset_root=tmp_path / "fixtures",
    ).image_href_resolver

    assert resolver.resolve_file("../images/pixel.png") == image
    assert resolver.resolve_file("../../outside.png") is None


def test_image_data_resolver_rejects_invalid_base64() -> None:
    resolver = build_default_options().image_href_resolver

    assert resolver.resolve_data("data:image/png;base64,NOT_VALID_BASE64!!!") is None
