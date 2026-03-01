"""feImage primitive helpers: URI decoding, image loading, RGBA conversion."""

from __future__ import annotations

import base64
import binascii
import io
import mimetypes
import urllib.parse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

try:  # pragma: no cover - optional dependency guard
    import skia
except ImportError:  # pragma: no cover
    skia = None

from svg2ooxml.core.resvg.usvg_tree import FilterPrimitive
from svg2ooxml.render.surface import Surface


class _Unsupported(Exception):
    """Thin wrapper so this module doesn't import UnsupportedPrimitiveError."""


def plan_image_primitive(
    primitive: FilterPrimitive,
    *,
    options: Mapping[str, Any] | None = None,
    error_cls: type[Exception] = _Unsupported,
) -> dict[str, Any]:
    """Parse an ``<feImage>`` primitive and return its decoded surface."""

    href = _extract_href(primitive.attributes)
    if not href:
        raise error_cls(primitive.tag, "feImage requires an href attribute", primitive=primitive)
    href = _normalize_href(href)
    if not href:
        raise error_cls(primitive.tag, "feImage requires an href attribute", primitive=primitive)
    try:
        mime, data = _decode_image_payload(href, options=options)
    except ValueError as exc:
        raise error_cls(primitive.tag, str(exc), primitive=primitive) from exc

    array = _decode_image_rgba(data, primitive, error_cls=error_cls)
    return {
        "surface": Surface(array.shape[1], array.shape[0], array),
        "mime": mime,
    }


def _extract_href(attrs: Mapping[str, str]) -> str | None:
    for key in ("href", "xlink:href", "{http://www.w3.org/1999/xlink}href"):
        value = attrs.get(key)
        if value:
            return value
    return None


def _decode_data_uri(uri: str) -> tuple[str | None, bytes]:
    if not uri.startswith("data:"):
        raise ValueError("external feImage references are not supported")
    header, _, payload = uri.partition(",")
    if not payload:
        raise ValueError("data URI is missing payload")
    meta = header[5:]  # strip "data:"
    is_base64 = ";base64" in meta
    if is_base64:
        try:
            data = base64.b64decode(payload.strip())
        except (ValueError, binascii.Error) as exc:
            raise ValueError("invalid base64 payload in data URI") from exc
    else:
        data = urllib.parse.unquote_to_bytes(payload)
    mime = None
    if meta:
        parts = [part for part in meta.split(";") if part]
        if parts:
            candidate = parts[0]
            if candidate != "base64":
                mime = candidate
    return mime, data


def _decode_image_payload(
    uri: str,
    *,
    options: Mapping[str, Any] | None = None,
) -> tuple[str | None, bytes]:
    if uri.startswith("data:"):
        return _decode_data_uri(uri)

    lowered = uri.lower()
    if lowered.startswith(("http://", "https://", "ftp://")):
        raise ValueError("external feImage URL references are not supported")
    if uri.startswith("#"):
        raise ValueError("fragment feImage references are not yet supported")

    source_path = _option_string(options, "source_path", "svg_path", "svg_file")
    if source_path is None:
        raise ValueError("external feImage references require source_path context")

    base_dir = Path(source_path).expanduser()
    if base_dir.suffix:
        base_dir = base_dir.parent
    target = Path(uri).expanduser()
    if not target.is_absolute():
        target = (base_dir / target).resolve()
    else:
        target = target.resolve()
    try:
        data = target.read_bytes()
    except (FileNotFoundError, OSError) as exc:
        raise ValueError(f"feImage resource not found: {uri}") from exc

    mime, _ = mimetypes.guess_type(target.name)
    return mime, data


def _decode_image_rgba(
    data: bytes,
    primitive: FilterPrimitive,
    *,
    error_cls: type[Exception] = _Unsupported,
) -> np.ndarray:
    if skia is not None:
        image = skia.Image.MakeFromEncoded(data)
        if image is None:
            raise error_cls(primitive.tag, "failed to decode feImage payload", primitive=primitive)

        try:
            pixels = image.tobytes()
        except Exception as exc:  # pragma: no cover - defensive
            raise error_cls(
                primitive.tag,
                "unable to extract feImage pixels",
                primitive=primitive,
            ) from exc

        array = (
            np.frombuffer(pixels, dtype=np.uint8)
            .reshape(image.height(), image.width(), 4)
            .astype(np.float32)
            / 255.0
        )
        # Handle platform-specific color channel ordering.
        if image.colorType() == skia.ColorType.kBGRA_8888_ColorType:
            array[:, :, [0, 2]] = array[:, :, [2, 0]]
        return array

    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - dependency guard
        raise error_cls(
            primitive.tag,
            "feImage decoding requires skia or Pillow",
            primitive=primitive,
        ) from exc

    try:
        with Image.open(io.BytesIO(data)) as image:
            rgba = image.convert("RGBA")
            array = np.asarray(rgba, dtype=np.float32) / 255.0
    except Exception as exc:
        raise error_cls(primitive.tag, "failed to decode feImage payload", primitive=primitive) from exc

    return array


def _normalize_href(value: str) -> str:
    token = value.strip()
    if token.lower().startswith("url(") and token.endswith(")"):
        token = token[4:-1].strip()
    if (token.startswith("'") and token.endswith("'")) or (
        token.startswith('"') and token.endswith('"')
    ):
        token = token[1:-1]
    return token.strip()


def _option_string(options: Mapping[str, Any] | None, *keys: str) -> str | None:
    if not isinstance(options, Mapping):
        return None
    for key in keys:
        value = options.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


__all__ = ["plan_image_primitive"]
