"""Service façade for color space conversions."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Tuple

from svg2ooxml.color.analysis import summarize_palette
from svg2ooxml.color.bridge import (
    ADVANCED_COLOR_ENGINE_AVAILABLE,
    ensure_advanced_color_engine,
)
from svg2ooxml.color.models import Color
from svg2ooxml.color.spaces import ColorSpaceConverter, ColorSpaceResult
from svg2ooxml.services.image_service import ImageResource


@dataclass(slots=True)
class ColorNormalizedImage:
    """Packaging of a normalised image alongside conversion metadata."""

    resource: ImageResource
    result: ColorSpaceResult


class ColorSpaceService:
    """Bridge service that normalises embedded images to sRGB."""

    def __init__(self, converter: ColorSpaceConverter | None = None) -> None:
        self._converter = converter or ColorSpaceConverter()

    @property
    def available(self) -> bool:
        return self._converter.available

    def normalize_bytes(
        self,
        data: bytes,
        *,
        mime_type: str | None = None,
        target_mode: str = "RGB",
    ) -> ColorSpaceResult:
        """Normalise raw bytes to the requested Pillow mode."""

        return self._converter.convert_bytes(
            data,
            mime_type=mime_type,
            target_mode=target_mode,
        )

    def normalize_resource(
        self,
        resource: ImageResource,
        *,
        normalization: str = "rgb",
    ) -> ColorNormalizedImage:
        """Return an updated ``ImageResource`` alongside conversion metadata."""

        if normalization == "skip":
            result = ColorSpaceResult(
                data=resource.data,
                mime_type=resource.mime_type or "application/octet-stream",
                mode=None,
                converted=False,
                warnings=["colorspace normalization skipped by policy"],
                metadata={"policy_normalization": "skip"},
            )
            return ColorNormalizedImage(resource=resource, result=result)

        target_mode = "RGBA" if normalization in {"full", "perceptual"} else "RGB"
        result = self.normalize_bytes(
            resource.data,
            mime_type=resource.mime_type,
            target_mode=target_mode,
        )

        metadata = dict(result.metadata)
        metadata.setdefault("policy_normalization", normalization)

        analysis_payload = result.data if result.converted else resource.data
        palette_stats = self._analyze_image_palette(analysis_payload)
        if palette_stats:
            metadata["palette"] = palette_stats

        if normalization == "perceptual":
            perceptual_meta = metadata.setdefault("perceptual", {})
            linearized = self._linearize_image(analysis_payload, mode="RGBA")
            if linearized is not None:
                linear_bytes, linear_meta = linearized
                perceptual_meta.update(linear_meta)
                result.data = linear_bytes
                result.mime_type = linear_meta.get("mime_type", "image/png")
                result.mode = linear_meta.get("mode", "RGBA")
                result.converted = True
            else:
                perceptual_meta.setdefault("applied", False)

        result.metadata = metadata

        if result.converted:
            updated = ImageResource(
                data=result.data,
                mime_type=result.mime_type,
                source=resource.source,
            )
        else:
            updated = resource
        return ColorNormalizedImage(resource=updated, result=result)

    def bind_services(self, _services: "ConversionServices") -> None:  # pragma: no cover - for DI consistency
        return

    def clone(self) -> "ColorSpaceService":
        return ColorSpaceService(self._converter)

    def _analyze_image_palette(self, payload: bytes) -> dict[str, object] | None:
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover - Pillow optional
            return None

        try:
            with Image.open(io.BytesIO(payload)) as image:
                working = image.convert("RGBA")
                width, height = working.size
                max_samples = 4096
                if width * height > max_samples:
                    scale = (max_samples / float(width * height)) ** 0.5
                    new_width = max(1, int(width * scale))
                    new_height = max(1, int(height * scale))
                    resampling = getattr(Image, "Resampling", None)
                    resample_filter = getattr(resampling, "BILINEAR", Image.BILINEAR) if resampling else Image.BILINEAR
                    working = working.resize((new_width, new_height), resample_filter)
                pixels = list(working.getdata())
        except Exception:
            return None

        if not pixels:
            return None

        max_samples = min(len(pixels), 4096)
        colours: list[Color] = []
        for pixel in pixels[:max_samples]:
            if len(pixel) == 4:
                r, g, b, a = pixel
            elif len(pixel) == 3:
                r, g, b = pixel
                a = 255
            else:
                continue
            colours.append(Color(r / 255.0, g / 255.0, b / 255.0, a / 255.0))
        return summarize_palette(colours)

    def _linearize_image(self, payload: bytes, *, mode: str) -> tuple[bytes, dict[str, object]] | None:
        if not ADVANCED_COLOR_ENGINE_AVAILABLE:
            return None
        try:
            ensure_advanced_color_engine()
            from PIL import Image
            import numpy as np
        except Exception:
            return None

        try:
            with Image.open(io.BytesIO(payload)) as image:
                working = image.convert(mode)
                output_mode = working.mode
                array = np.asarray(working).astype("float32") / 255.0
                rgb = array[..., :3]
                mask = rgb <= 0.04045
                rgb[mask] = rgb[mask] / 12.92
                rgb[~mask] = np.power((rgb[~mask] + 0.055) / 1.055, 2.4)
                array[..., :3] = rgb
                array = np.clip(array * 255.0 + 0.5, 0.0, 255.0).astype("uint8")
                linear_image = Image.fromarray(array, mode=output_mode)
                buffer = io.BytesIO()
                linear_image.save(buffer, format="PNG")
        except Exception:
            return None

        return buffer.getvalue(), {
            "applied": True,
            "space": "linear_rgb",
            "mode": output_mode,
            "mime_type": "image/png",
        }


__all__ = ["ColorNormalizedImage", "ColorSpaceService"]
