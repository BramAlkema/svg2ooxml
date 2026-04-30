"""Style extraction helpers for the IR converter."""

from __future__ import annotations

from dataclasses import replace

from lxml import etree

from svg2ooxml.common.svg_refs import local_name, local_url_id
from svg2ooxml.core.styling.pattern_merge import (
    merge_pattern_paint as _merge_pattern_paint,
)
from svg2ooxml.core.styling.style_helpers import parse_style_attr
from svg2ooxml.ir.paint import PatternPaint, SolidPaint
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

    # Fallback: map <use> elements to their referenced source nodes.
    if resvg_node is None:
        tag_name = local_name(element.tag)
        if tag_name.lower() == "use":
            href_attr = element.get(
                "{http://www.w3.org/1999/xlink}href"
            ) or element.get("href")
            reference_id = local_url_id(href_attr)
            if reference_id is not None:
                element_index = getattr(converter, "_element_index", None)
                if isinstance(element_index, dict):
                    source_element = element_index.get(reference_id)
                    if isinstance(source_element, etree._Element):
                        resvg_node = node_lookup.get(source_element)

    if resvg_node is None:
        logger = getattr(converter, "_logger", None)
        if logger is not None:
            # Only warn for drawable elements that SHOULD be in the resvg tree.
            # Elements inside <defs> or other non-drawable containers are expected to be missing.
            tag_name = local_name(element.tag)
            is_drawable = tag_name.lower() in {
                "path",
                "rect",
                "circle",
                "ellipse",
                "line",
                "polyline",
                "polygon",
                "image",
                "text",
                "g",
                "svg",
                "use",
            }

            # Check if element or any ancestor is inside <defs>
            in_defs = False
            curr = element
            while curr is not None:
                local_tag = local_name(curr.tag).lower()
                if local_tag == "defs":
                    in_defs = True
                    break
                if curr.get("data-svg2ooxml-use-clone") == "true":
                    # Cloned <use> instances are expected to be missing from resvg.
                    return StyleResult(
                        fill=base_style.fill,
                        stroke=base_style.stroke,
                        opacity=base_style.opacity,
                        effects=base_style.effects,
                        metadata=metadata,
                    )
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
                        extra={
                            "element_id": element.get("id"),
                            "svg_tag": str(element.tag),
                        },
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

    fill_disabled = _element_explicitly_disables_paint(element, "fill")
    stroke_disabled = _element_explicitly_disables_paint(element, "stroke")

    fill = (
        None
        if fill_disabled
        else (paints.fill if paints.fill is not None else base_style.fill)
    )
    if isinstance(fill, PatternPaint) and isinstance(base_style.fill, PatternPaint):
        fill = _merge_pattern_paint(fill, base_style.fill)
    elif isinstance(fill, PatternPaint) and isinstance(base_style.fill, SolidPaint):
        fill = base_style.fill

    stroke = (
        None
        if stroke_disabled
        else _merge_resvg_stroke(paints.stroke, base_style.stroke)
    )
    if (
        stroke is not None
        and base_style.stroke is not None
        and isinstance(getattr(stroke, "paint", None), PatternPaint)
        and isinstance(getattr(base_style.stroke, "paint", None), PatternPaint)
    ):
        stroke = replace(
            stroke, paint=_merge_pattern_paint(stroke.paint, base_style.stroke.paint)
        )
    elif (
        stroke is not None
        and base_style.stroke is not None
        and isinstance(getattr(stroke, "paint", None), PatternPaint)
        and isinstance(getattr(base_style.stroke, "paint", None), SolidPaint)
    ):
        stroke = replace(stroke, paint=base_style.stroke.paint)

    opacity = base_style.opacity
    presentation = getattr(resvg_node, "presentation", None)
    if presentation is not None and getattr(presentation, "opacity", None) is not None:
        opacity = presentation.opacity  # type: ignore[assignment]

    style_meta["source"] = "resvg"
    decision = resolve_fidelity(
        "style", node=resvg_node, context={"element_id": element.get("id")}
    )
    style_meta["decision"] = decision.value
    return StyleResult(
        fill=fill,
        stroke=stroke,
        opacity=opacity,
        effects=base_style.effects,
        metadata=metadata,
    )


__all__ = ["extract_style"]


def _merge_resvg_stroke(resvg_stroke, base_stroke):
    if resvg_stroke is None:
        return base_stroke
    if base_stroke is None:
        return resvg_stroke

    updates = {}
    if resvg_stroke.dash_array is None and base_stroke.dash_array is not None:
        updates["dash_array"] = base_stroke.dash_array
    if resvg_stroke.dash_offset in (None, 0.0) and base_stroke.dash_offset not in (
        None,
        0.0,
    ):
        updates["dash_offset"] = base_stroke.dash_offset
    if resvg_stroke.cap.value == "butt" and base_stroke.cap.value != "butt":
        updates["cap"] = base_stroke.cap
    if resvg_stroke.join.value == "miter" and base_stroke.join.value != "miter":
        updates["join"] = base_stroke.join
    if resvg_stroke.miter_limit == 4.0 and base_stroke.miter_limit != 4.0:
        updates["miter_limit"] = base_stroke.miter_limit
    if updates:
        return replace(resvg_stroke, **updates)
    return resvg_stroke


def _element_explicitly_disables_paint(
    element: etree._Element,
    attribute: str,
) -> bool:
    attr_value = element.get(attribute)
    if isinstance(attr_value, str) and attr_value.strip().lower() == "none":
        return True
    style_attr = element.get("style")
    if not isinstance(style_attr, str) or attribute not in style_attr:
        return False
    parsed = parse_style_attr(style_attr)
    value = parsed.get(attribute)
    return isinstance(value, str) and value.strip().lower() == "none"
