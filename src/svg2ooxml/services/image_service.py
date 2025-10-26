"""Simple image resolution service."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Callable, Sequence

DATA_URI_RE = re.compile(r"^data:(?P<mime>[^;]+)?(;base64)?,(?P<payload>.+)$")


@dataclass(frozen=True)
class ImageResource:
    """Resolved image payload."""

    data: bytes
    mime_type: str | None = None
    source: str | None = None


Resolver = Callable[[str], ImageResource | None]


class ImageService:
    """Resolve image hrefs to binary payloads."""

    def __init__(self) -> None:
        self._resolvers: list[Resolver] = [self._data_uri_resolver]

    def bind_services(self, _services: "ConversionServices") -> None:  # pragma: no cover - signature used by container
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
        for resolver in self._resolvers:
            result = resolver(href)
            if result is not None:
                return result
        return None

    def clone(self) -> "ImageService":
        clone = ImageService()
        clone._resolvers = list(self._resolvers)
        return clone

    @staticmethod
    def _data_uri_resolver(href: str) -> ImageResource | None:
        match = DATA_URI_RE.match(href)
        if not match:
            return None
        mime_type = match.group("mime") or None
        payload = match.group("payload")
        if ";base64," in href:
            data = base64.b64decode(payload, validate=True)
        else:
            data = payload.encode("utf-8")
        return ImageResource(data=data, mime_type=mime_type, source="data-uri")


__all__ = ["ImageResource", "ImageService", "Resolver"]
