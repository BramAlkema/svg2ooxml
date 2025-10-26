"""Style extraction helpers for the IR converter."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.paint.resvg_bridge import resolve_paints_for_node

from .styles import StyleResult


def extract_style(converter, element: etree._Element) -> StyleResult:
    """Return the StyleResult for ``element`` using converter context."""

    base_style: StyleResult = converter._style_extractor.extract(
        element,
        converter._services,
        context=converter._css_context,
    )

    resvg_tree = getattr(converter, "_resvg_tree", None)
    if not resvg_tree:
        return base_style

    node_lookup = getattr(converter, "_resvg_element_lookup", {})
    resvg_node = node_lookup.get(element)
    if resvg_node is None:
        return base_style

    try:
        paints = resolve_paints_for_node(resvg_node, resvg_tree)
    except Exception:  # pragma: no cover - bridge may fail during porting
        return base_style

    fill = paints.fill if paints.fill is not None else base_style.fill
    stroke = paints.stroke if paints.stroke is not None else base_style.stroke

    opacity = base_style.opacity
    presentation = getattr(resvg_node, "presentation", None)
    if presentation is not None and getattr(presentation, "opacity", None) is not None:
        opacity = presentation.opacity  # type: ignore[assignment]

    return StyleResult(
        fill=fill,
        stroke=stroke,
        opacity=opacity,
        effects=base_style.effects,
        metadata=dict(base_style.metadata),
    )


__all__ = ["extract_style"]
