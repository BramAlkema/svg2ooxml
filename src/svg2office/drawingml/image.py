"""Picture rendering helpers for DrawingML writer."""

from __future__ import annotations

from svg2office.common.office_profile import (
    EXT_URI_SVG_BLIP,
    EXT_URI_USE_LOCAL_DPI,
    USE_LOCAL_DPI_VALUE,
)
from svg2office.drawingml.generator import px_to_emu
from svg2office.ir.scene import Image


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

    blip_extensions = None
    if callable(lookup_blip_extensions):
        blip_extensions = lookup_blip_extensions(r_id)
    blip_extensions_xml = _blip_extensions_xml(blip_extensions)

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
    )


def _indent_block(xml: str, indent: str = "        ") -> str:
    if not xml:
        return ""
    lines = xml.splitlines()
    return "".join(f"{indent}{line}\n" for line in lines)


def _blip_extensions_xml(blip_extensions: object) -> str:
    if not isinstance(blip_extensions, dict):
        return ""
    svg_relationship_id = blip_extensions.get("svg_relationship_id")
    if not isinstance(svg_relationship_id, str) or not svg_relationship_id:
        return ""
    use_local_dpi = blip_extensions.get("use_local_dpi", USE_LOCAL_DPI_VALUE)
    try:
        use_local_dpi_value = int(use_local_dpi)
    except (TypeError, ValueError):
        use_local_dpi_value = USE_LOCAL_DPI_VALUE
    return (
        "\n"
        "            <a:extLst>\n"
        f'                <a:ext uri="{EXT_URI_SVG_BLIP}">\n'
        f'                    <asvg:svgBlip r:embed="{svg_relationship_id}"/>\n'
        "                </a:ext>\n"
        f'                <a:ext uri="{EXT_URI_USE_LOCAL_DPI}">\n'
        f'                    <a14:useLocalDpi val="{use_local_dpi_value}"/>\n'
        "                </a:ext>\n"
        "            </a:extLst>\n"
        "        "
    )


__all__ = ["render_picture"]
