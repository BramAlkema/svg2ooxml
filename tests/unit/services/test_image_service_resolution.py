from __future__ import annotations

from svg2ooxml.services.image_service import (
    FileResolver,
    ImageService,
    normalize_image_href,
    resolve_local_image_path,
)


def test_image_service_percent_decodes_plain_data_uri() -> None:
    service = ImageService()

    resource = service.resolve("data:text/plain,hello%20world")

    assert resource is not None
    assert resource.data == b"hello world"
    assert resource.mime_type == "text/plain"
    assert resource.source == "data-uri"


def test_image_service_base64_data_uri_is_case_insensitive() -> None:
    service = ImageService()

    resource = service.resolve("DATA:image/png;BASE64,Zm9v")

    assert resource is not None
    assert resource.data == b"foo"
    assert resource.mime_type == "image/png"


def test_image_service_base64_data_uri_ignores_attribute_whitespace() -> None:
    service = ImageService()

    resource = service.resolve("data:image/png;base64, Zm9v\n YmFy ")

    assert resource is not None
    assert resource.data == b"foobar"


def test_image_service_rejects_invalid_base64_data_uri() -> None:
    service = ImageService()

    assert service.resolve("data:image/png;base64,not-valid!") is None


def test_normalize_image_href_unwraps_css_url() -> None:
    assert normalize_image_href(" url('assets/pixel.png') ") == "assets/pixel.png"


def test_file_resolver_resolves_inside_asset_root(tmp_path) -> None:
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    image_path = asset_root / "pixel.png"
    image_path.write_bytes(b"png")
    resolver = FileResolver(asset_root, asset_root=asset_root)

    resource = resolver("url('pixel.png')")

    assert resource is not None
    assert resource.data == b"png"
    assert resource.source == "file"


def test_file_resolver_rejects_paths_outside_asset_root(tmp_path) -> None:
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"png")
    resolver = FileResolver(asset_root, asset_root=asset_root)

    assert resolver("../outside.png") is None
    assert resolver(str(outside)) is None
    assert resolver(outside.as_uri()) is None


def test_file_resolver_default_root_is_base_dir(tmp_path) -> None:
    asset_dir = tmp_path / "svg"
    asset_dir.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"png")
    resolver = FileResolver(asset_dir)

    assert resolver("../outside.png") is None
    assert resolver(str(outside)) is None


def test_file_resolver_can_opt_into_parent_asset_root(tmp_path) -> None:
    svg_dir = tmp_path / "svg"
    svg_dir.mkdir()
    image_path = tmp_path / "images" / "pixel.png"
    image_path.parent.mkdir()
    image_path.write_bytes(b"png")
    resolver = FileResolver(svg_dir, asset_root=tmp_path)

    resource = resolver("../images/pixel.png")

    assert resource is not None
    assert resource.data == b"png"


def test_resolve_local_image_path_rejects_external_and_fragment_hrefs(tmp_path) -> None:
    asset_root = tmp_path / "assets"
    asset_root.mkdir()

    assert resolve_local_image_path("https://example.com/pixel.png", asset_root) is None
    assert resolve_local_image_path("ftp://example.com/pixel.png", asset_root) is None
    assert resolve_local_image_path("#image", asset_root) is None
