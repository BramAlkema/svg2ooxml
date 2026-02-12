"""Simple image resolution service."""

from __future__ import annotations

import base64
import os
import re
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from svg2ooxml.services import ConversionServices

DATA_URI_RE = re.compile(r"^data:(?P<mime>[^;]+)?(;base64)?,(?P<payload>.+)$")


@dataclass(frozen=True)
class ImageResource:
    """Resolved image payload."""

    data: bytes
    mime_type: str | None = None
    source: str | None = None


Resolver = Callable[[str], ImageResource | None]


class FileResolver:
    """Resolve image hrefs from the local filesystem."""

    def __init__(self, base_dir: Path | str) -> None:
        self._base_dir = Path(base_dir).resolve()

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def __call__(self, href: str) -> ImageResource | None:
        if DATA_URI_RE.match(href):
            return None

        # Try relative to base dir
        try:
            target = (self._base_dir / href).resolve()
            if target.is_file():
                return ImageResource(
                    data=target.read_bytes(),
                    source="file",
                )
        except Exception:
            return None
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
        cached = self._cache_get(href)
        if cached is not None:
            return cached
        for resolver in self._resolvers:
            result = resolver(href)
            if result is not None:
                self._cache_put(href, result)
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
        match = DATA_URI_RE.match(href)
        if not match:
            return None
        mime_type = match.group("mime") or None
        payload = match.group("payload").strip()
        if ";base64," in href:
            data = base64.b64decode(payload)
        else:
            data = payload.encode("utf-8")
        return ImageResource(data=data, mime_type=mime_type, source="data-uri")

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


__all__ = ["ImageResource", "ImageService", "Resolver"]
