from __future__ import annotations

from svg2ooxml.services.image_service import ImageResource, ImageService


def test_image_service_caches_resolver_results() -> None:
    calls: list[str] = []

    def resolver(href: str) -> ImageResource | None:
        calls.append(href)
        return ImageResource(data=b"payload", source="test")

    service = ImageService(cache_max_items=4, cache_max_bytes=1024)
    service.register_resolver(resolver, prepend=True)

    assert service.resolve("asset.png") is not None
    assert service.resolve("asset.png") is not None

    assert calls == ["asset.png"]
