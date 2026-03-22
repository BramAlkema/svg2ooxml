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
    lookup_blip_extensions=None,
    hyperlink_xml: str = "",
    geometry_xml: str = "",
) -> str | None:
    """Render an IR image element into a picture shape."""
    from .shapes_runtime import _descr_attr, _effect_block  # lazy to avoid cycle

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
        effects_xml = _indent_block(_effect_block(getattr(image, "effects", [])))

    # srcRect from clip bounds (thousandths of percent).
    src_rect = image.metadata.get("_src_rect")
    if isinstance(src_rect, tuple) and len(src_rect) == 4:
        src_rect_xml = (
            f'        <a:srcRect l="{src_rect[0]}" t="{src_rect[1]}"'
            f' r="{src_rect[2]}" b="{src_rect[3]}"/>\n'
        )
    else:
        src_rect_xml = ""

    # Geometry: clip shape or default rectangle.
    if not geometry_xml:
        geometry_xml = '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'

    blip_extensions_xml = ""
    if callable(lookup_blip_extensions):
        blip_extensions = lookup_blip_extensions(r_id)
        if isinstance(blip_extensions, str):
            blip_extensions_xml = blip_extensions
        elif blip_extensions:
            blip_extensions_xml = str(blip_extensions)

    return template.format(
        SHAPE_ID=shape_id,
        SHAPE_NAME=shape_name,
        R_ID=r_id,
        BLIP_EXTENSIONS_XML=blip_extensions_xml,
        X_EMU=px_to_emu(origin.x),
        Y_EMU=px_to_emu(origin.y),
        WIDTH_EMU=px_to_emu(width),
        HEIGHT_EMU=px_to_emu(height),
        EFFECTS_XML=effects_xml,
        HYPERLINK_XML=_indent_block(hyperlink_xml),
        SRC_RECT_XML=src_rect_xml,
        GEOMETRY_XML=geometry_xml,
        DESCR_ATTR=_descr_attr(image.metadata),
    )


def _indent_block(xml: str, indent: str = "        ") -> str:
    if not xml:
        return ""
    lines = xml.splitlines()
    return "".join(f"{indent}{line}\n" for line in lines)


__all__ = ["render_picture"]
