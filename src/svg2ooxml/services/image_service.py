"""Simple image resolution service."""

from __future__ import annotations

import os
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from svg2ooxml.common.boundaries import (
    DATA_URI_RE,
    EXTERNAL_RESOURCE_SCHEMES,
    decode_data_uri,
    is_external_resource_href,
    normalize_resource_href,
    resolve_local_resource_path,
)

if TYPE_CHECKING:
    from svg2ooxml.services import ConversionServices

EXTERNAL_IMAGE_PROTOCOLS = EXTERNAL_RESOURCE_SCHEMES


@dataclass(frozen=True)
class ImageResource:
    """Resolved image payload."""

    data: bytes
    mime_type: str | None = None
    source: str | None = None


Resolver = Callable[[str], ImageResource | None]


class FileResolver:
    """Resolve image hrefs from the local filesystem."""

    def __init__(self, base_dir: Path | str, *, asset_root: Path | str | None = None) -> None:
        self._base_dir = Path(base_dir).expanduser().resolve()
        root = asset_root if asset_root is not None else self._base_dir
        self._asset_root = Path(root).expanduser().resolve()

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def asset_root(self) -> Path:
        return self._asset_root

    def __call__(self, href: str) -> ImageResource | None:
        target = resolve_local_image_path(
            href,
            self._base_dir,
            asset_root=self._asset_root,
        )
        if target is None:
            return None
        try:
            return ImageResource(
                data=target.read_bytes(),
                source="file",
            )
        except OSError:
            return None


class ImageService:
    """Resolve image hrefs to binary payloads."""

    def __init__(
        self,
        *,
        cache_max_items: int | None = None,
        cache_max_bytes: int | None = None,
    ) -> None:
        self._resolvers: list[Resolver] = [self._data_uri_resolver]
        self._cache: OrderedDict[str, ImageResource] = OrderedDict()
        self._cache_bytes = 0
        self._cache_max_items = _env_int("SVG2OOXML_IMAGE_CACHE_SIZE", 256) if cache_max_items is None else cache_max_items
        self._cache_max_bytes = (
            _env_int("SVG2OOXML_IMAGE_CACHE_BYTES", 64 * 1024 * 1024)
            if cache_max_bytes is None
            else cache_max_bytes
        )

    def bind_services(self, _services: ConversionServices) -> None:  # pragma: no cover - signature used by container
        # Image service currently does not depend on other services, but we keep
        # the hook for parity with other services.
        return

    def register_resolver(self, resolver: Resolver, *, prepend: bool = False) -> None:
        """Add an image resolver callable.

        Resolvers are tried in order; pass ``prepend=True`` to take priority.
        """
        if prepend:
            self._resolvers.insert(0, resolver)
        else:
            self._resolvers.append(resolver)

    def resolvers(self) -> Sequence[Resolver]:
        """Return registered resolvers in resolution order."""
        return tuple(self._resolvers)

    def resolve(self, href: str) -> ImageResource | None:
        """Try each resolver until one returns a payload."""
        normalized_href = normalize_image_href(href)
        if not normalized_href:
            return None
        cached = self._cache_get(normalized_href)
        if cached is not None:
            return cached
        for resolver in self._resolvers:
            result = resolver(normalized_href)
            if result is not None:
                self._cache_put(normalized_href, result)
                return result
        return None

    def clone(self) -> ImageService:
        clone = ImageService(
            cache_max_items=self._cache_max_items,
            cache_max_bytes=self._cache_max_bytes,
        )
        clone._resolvers = list(self._resolvers)
        clone._cache = OrderedDict(self._cache)
        clone._cache_bytes = self._cache_bytes
        return clone

    @staticmethod
    def _data_uri_resolver(href: str) -> ImageResource | None:
        normalized_href = normalize_image_href(href)
        if not normalized_href:
            return None
        decoded = decode_data_uri(normalized_href)
        if decoded is None:
            return None
        return ImageResource(
            data=decoded.data,
            mime_type=decoded.mime_type,
            source="data-uri",
        )

    def _cache_enabled(self) -> bool:
        return self._cache_max_items > 0 and self._cache_max_bytes > 0

    def _cache_get(self, href: str) -> ImageResource | None:
        if not self._cache_enabled():
            return None
        cached = self._cache.get(href)
        if cached is None:
            return None
        self._cache.move_to_end(href)
        return cached

    def _cache_put(self, href: str, resource: ImageResource) -> None:
        if not self._cache_enabled():
            return
        data = resource.data or b""
        size = len(data)
        if size <= 0:
            return
        if size > self._cache_max_bytes:
            return

        if href in self._cache:
            existing = self._cache.pop(href)
            self._cache_bytes -= len(existing.data or b"")

        while (
            self._cache
            and (self._cache_bytes + size > self._cache_max_bytes or len(self._cache) >= self._cache_max_items)
        ):
            _, evicted = self._cache.popitem(last=False)
            self._cache_bytes -= len(evicted.data or b"")

        self._cache[href] = resource
        self._cache_bytes += size


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def normalize_image_href(href: str | None) -> str | None:
    """Normalize common SVG/CSS href wrappers for image resolution."""

    return normalize_resource_href(href)


def is_external_image_href(href: str | None) -> bool:
    """Return true for hrefs that must not be resolved from local disk."""

    return is_external_resource_href(href)


def resolve_local_image_path(
    href: str | None,
    base_dir: Path | str,
    *,
    asset_root: Path | str | None = None,
) -> Path | None:
    """Resolve a local image path without allowing absolute or ``..`` escapes."""

    return resolve_local_resource_path(href, base_dir, asset_root=asset_root)


__all__ = [
    "DATA_URI_RE",
    "EXTERNAL_IMAGE_PROTOCOLS",
    "FileResolver",
    "ImageResource",
    "ImageService",
    "Resolver",
    "is_external_image_href",
    "normalize_image_href",
    "resolve_local_image_path",
]
