"""Picture rendering helpers for DrawingML writer."""

from __future__ import annotations

from svg2ooxml.drawingml.generator import px_to_emu
from svg2ooxml.ir.scene import Image


def render_picture(
    image: Image,
    shape_id: int,
    *,
    template: str,
    policy_for,
    register_media,
    hyperlink_xml: str = "",
    clip_path_xml: str = "",
    mask_xml: str = "",
) -> str | None:
    """Render an IR image element into a picture shape."""

    if image.data is None and image.href is None:
        return None

    r_id = register_media(image)
    if not r_id:
        return None
    origin = image.origin
    bounds = image.size
    width = max(bounds.width, 1.0)
    height = max(bounds.height, 1.0)

    shape_name = f"Picture {shape_id}"
    policy_meta = (
        policy_for(image.metadata, "geometry")
        or policy_for(image.metadata, "text")
        or policy_for(image.metadata, "image")
    )
    if policy_meta:
        suffix = ", ".join(f"{key}={value}" for key, value in sorted(policy_meta.items()))
        shape_name += f" ({suffix})"

    effects_xml = ""
    if isinstance(getattr(image, "effects", []), list):
        from .shapes_runtime import _effect_block  # lazy import to avoid cycle

        effects_xml = _indent_block(_effect_block(getattr(image, "effects", [])))

    return template.format(
        SHAPE_ID=shape_id,
        SHAPE_NAME=shape_name,
        R_ID=r_id,
        X_EMU=px_to_emu(origin.x),
        Y_EMU=px_to_emu(origin.y),
        WIDTH_EMU=px_to_emu(width),
        HEIGHT_EMU=px_to_emu(height),
        EFFECTS_XML=effects_xml,
        HYPERLINK_XML=_indent_block(hyperlink_xml),
        CLIP_PATH_XML=_indent_block(clip_path_xml),
        MASK_XML=_indent_block(mask_xml),
    )


def _indent_block(xml: str, indent: str = "        ") -> str:
    if not xml:
        return ""
    lines = xml.splitlines()
    return "".join(f"{indent}{line}\n" for line in lines)


__all__ = ["render_picture"]
