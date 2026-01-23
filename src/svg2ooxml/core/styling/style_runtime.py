"""Style extraction helpers for the IR converter."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.paint.resvg_bridge import resolve_paints_for_node
from svg2ooxml.policy.fidelity import FidelityDecision, resolve_fidelity

from .style_extractor import StyleResult


def extract_style(converter, element: etree._Element) -> StyleResult:
    """Return the StyleResult for ``element`` using converter context."""

    base_style: StyleResult = converter._style_extractor.extract(
        element,
        converter._services,
        context=converter._css_context,
    )

    resvg_tree = getattr(converter, "_resvg_tree", None)
    metadata = dict(base_style.metadata)
    style_meta = metadata.setdefault("style", {})
    style_meta["source"] = "legacy"
    style_meta["decision"] = FidelityDecision.NATIVE.value
    if not resvg_tree:
        return StyleResult(
            fill=base_style.fill,
            stroke=base_style.stroke,
            opacity=base_style.opacity,
            effects=base_style.effects,
            metadata=metadata,
        )

    node_lookup = getattr(converter, "_resvg_element_lookup", {})
    resvg_node = node_lookup.get(element)

    if resvg_node is None:
        logger = getattr(converter, "_logger", None)
        if logger is not None:
            # Only warn for drawable elements that SHOULD be in the resvg tree.
            # Elements inside <defs> or other non-drawable containers are expected to be missing.
            tag_name = str(element.tag).split("}", 1)[-1]
            is_drawable = tag_name.lower() in {
                "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "image", "text", "g", "svg", "use"
            }
            
            # Check if element or any ancestor is inside <defs>
            in_defs = False
            curr = element
            while curr is not None:
                local_tag = str(curr.tag).split("}", 1)[-1].lower()
                if local_tag == "defs":
                    in_defs = True
                    break
                curr = curr.getparent()

            if is_drawable and not in_defs:
                # Also check if it's a child of an element that IS in the resvg tree
                # (Sometimes resvg groups things differently)
                parent_has_node = False
                p = element.getparent()
                if p is not None and p in node_lookup:
                    parent_has_node = True
                
                if not parent_has_node:
                    logger.warning(
                        "style-runtime/missing-resvg-node",
                        extra={"element_id": element.get("id"), "svg_tag": str(element.tag)},
                    )
        return StyleResult(
            fill=base_style.fill,
            stroke=base_style.stroke,
            opacity=base_style.opacity,
            effects=base_style.effects,
            metadata=metadata,
        )

    try:
        paints = resolve_paints_for_node(resvg_node, resvg_tree)
    except Exception:  # pragma: no cover - bridge may fail during porting
        return StyleResult(
            fill=base_style.fill,
            stroke=base_style.stroke,
            opacity=base_style.opacity,
            effects=base_style.effects,
            metadata=metadata,
        )

    fill = paints.fill if paints.fill is not None else base_style.fill
    stroke = paints.stroke if paints.stroke is not None else base_style.stroke

    opacity = base_style.opacity
    presentation = getattr(resvg_node, "presentation", None)
    if presentation is not None and getattr(presentation, "opacity", None) is not None:
        opacity = presentation.opacity  # type: ignore[assignment]

    style_meta["source"] = "resvg"
    decision = resolve_fidelity("style", node=resvg_node, context={"element_id": element.get("id")})
    style_meta["decision"] = decision.value
    return StyleResult(
        fill=fill,
        stroke=stroke,
        opacity=opacity,
        effects=base_style.effects,
        metadata=metadata,
    )


__all__ = ["extract_style"]
