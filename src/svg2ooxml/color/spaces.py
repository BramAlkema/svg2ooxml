"""Color space conversion helpers with optional Pillow support."""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass, field

try:  # pragma: no cover - optional dependency
    from PIL import Image, ImageCms, UnidentifiedImageError

    PIL_AVAILABLE = True
except Exception:  # pragma: no cover - Pillow is optional
    Image = None  # type: ignore[assignment]
    ImageCms = None  # type: ignore[assignment]
    UnidentifiedImageError = Exception  # type: ignore[assignment]
    PIL_AVAILABLE = False


_FORMAT_MIME_MAP: dict[str, str] = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "JPG": "image/jpeg",
    "TIFF": "image/tiff",
    "BMP": "image/bmp",
    "GIF": "image/gif",
    "WEBP": "image/webp",
}


@dataclass(slots=True)
class ColorSpaceResult:
    """Outcome of a color space conversion attempt."""

    data: bytes
    mime_type: str
    mode: str | None
    converted: bool
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


class ColorSpaceConverter:
    """Thin façade over Pillow's colorspace helpers."""

    def __init__(self, *, force_disable: bool = False) -> None:
        self._available = bool(PIL_AVAILABLE and not force_disable)

    @property
    def available(self) -> bool:
        return self._available

    def convert_bytes(
        self,
        payload: bytes,
        *,
        mime_type: str | None = None,
        target_mode: str = "RGB",
    ) -> ColorSpaceResult:
        """Convert raw image bytes to the requested Pillow mode."""

        warnings: list[str] = []
        metadata: dict[str, object] = {"target_mode": target_mode}
        if not self.available:
            warnings.append("Pillow not available; skipping colorspace conversion.")
            return ColorSpaceResult(
                data=payload,
                mime_type=mime_type or "application/octet-stream",
                mode=None,
                converted=False,
                warnings=warnings,
                metadata=metadata | {"reason": "converter_unavailable"},
            )

        assert Image is not None  # for type checkers
        assert ImageCms is not None

        try:
            image = Image.open(io.BytesIO(payload))
            image.load()
            metadata.update(
                {
                    "source_mode": image.mode,
                    "source_format": image.format,
                }
            )
            if "icc_profile_name" in image.info:
                metadata["source_profile_name"] = image.info["icc_profile_name"]
            if "icc_profile" in image.info:
                metadata["has_icc_profile"] = True
        except UnidentifiedImageError as exc:  # pragma: no cover - depends on Pillow
            warnings.append(f"could not identify image: {exc}")
            return ColorSpaceResult(
                data=payload,
                mime_type=mime_type or "application/octet-stream",
                mode=None,
                converted=False,
                warnings=warnings,
                metadata=metadata | {"reason": "unidentified_image"},
            )
        except Exception as exc:  # pragma: no cover - depends on Pillow internals
            warnings.append(f"failed to read image: {exc}")
            return ColorSpaceResult(
                data=payload,
                mime_type=mime_type or "application/octet-stream",
                mode=None,
                converted=False,
                warnings=warnings,
                metadata=metadata | {"reason": "read_failure"},
            )

        converted = False
        working = image
        try:
            icc_profile = working.info.get("icc_profile")
            if icc_profile and hasattr(ImageCms, "profileToProfile"):
                try:
                    src_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc_profile))
                    dst_profile = ImageCms.createProfile("sRGB")
                    working = ImageCms.profileToProfile(
                        working, src_profile, dst_profile, outputMode=target_mode
                    )
                    converted = True
                except Exception as exc:  # pragma: no cover - rare profile issues
                    warnings.append(f"icc conversion failed: {exc}")

            if working.mode != target_mode:
                try:
                    working = working.convert(target_mode)
                    converted = True
                except ValueError as exc:
                    warnings.append(f"unsupported mode conversion: {exc}")

            if not converted:
                return ColorSpaceResult(
                    data=payload,
                    mime_type=mime_type or self._preferred_mime(working.format),
                    mode=working.mode,
                    converted=False,
                    warnings=warnings,
                    metadata=metadata | {
                        "output_mode": working.mode,
                        "output_format": working.format,
                    },
                )

            output = io.BytesIO()
            save_format = self._select_format(
                working.format or image.format, target_mode, mime_type
            )
            self._save_image(working, output, save_format)
            data = output.getvalue()
            metadata.update(
                {
                    "output_mode": working.mode,
                    "output_format": save_format,
                }
            )
            return ColorSpaceResult(
                data=data,
                mime_type=self._preferred_mime(save_format),
                mode=working.mode,
                converted=True,
                warnings=warnings,
                metadata=metadata,
            )
        finally:
            if working is not image and hasattr(working, "close"):
                working.close()
            image.close()

    # ------------------------------------------------------------------ #
    # internal helpers
    # ------------------------------------------------------------------ #

    def _select_format(
        self,
        original_format: str | None,
        target_mode: str,
        mime_type: str | None,
    ) -> str:
        preferred: Iterable[str] = ()
        if mime_type:
            preferred = (self._mime_to_format(mime_type),)
        if not preferred and original_format:
            preferred = (original_format,)

        for candidate in preferred:
            if not candidate:
                continue
            upper = candidate.upper()
            if target_mode in {"RGB", "RGBA"} or upper not in {"PNG", "JPEG", "JPG"}:
                return upper
        return "PNG" if target_mode in {"RGB", "RGBA"} else (original_format or "PNG")

    def _preferred_mime(self, format_name: str | None) -> str:
        if not format_name:
            return "application/octet-stream"
        return _FORMAT_MIME_MAP.get(format_name.upper(), "application/octet-stream")

    def _mime_to_format(self, mime_type: str) -> str:
        reverse = {v: k for k, v in _FORMAT_MIME_MAP.items()}
        return reverse.get(mime_type.lower(), "PNG")

    def _save_image(self, image, buffer: io.BytesIO, format_name: str) -> None:
        params: dict[str, object] = {}
        if format_name.upper() in {"JPEG", "JPG"}:
            params.setdefault("quality", 95)
        image.save(buffer, format=format_name, **params)


__all__ = ["ColorSpaceConverter", "ColorSpaceResult", "PIL_AVAILABLE"]
