"""ID indexing and ``<use>`` expansion for typed usvg trees."""

from __future__ import annotations

import copy
from dataclasses import replace

from .geometry.matrix import Matrix
from .painting.paint import resolve_stroke
from .usvg_nodes import BaseNode, UseNode
from .usvg_nodes import propagate_use_source as _propagate_use_source


def collect_ids(node: BaseNode, ids: dict[str, BaseNode]) -> None:
    if node.id:
        ids[node.id] = node
    for child in node.children:
        collect_ids(child, ids)


def clear_ids(node: BaseNode) -> None:
    node.id = None
    for child in node.children:
        clear_ids(child)


def expand_use_nodes(root: BaseNode, ids: dict[str, BaseNode]) -> None:
    stack: list[tuple[BaseNode, tuple[str, ...]]] = [(root, ())]
    while stack:
        current, active_refs = stack.pop()
        for index, child in enumerate(list(current.children)):
            if isinstance(child, UseNode) and child.href:
                clone = _expand_use_child(child, ids, active_refs)
                if clone is None:
                    continue
                current.children[index] = clone
                if child.id:
                    ids[child.id] = clone
                stack.append((clone, (*active_refs, child.href.lstrip("#"))))
            else:
                stack.append((child, active_refs))


def _expand_use_child(
    child: UseNode,
    ids: dict[str, BaseNode],
    active_refs: tuple[str, ...],
) -> BaseNode | None:
    ref_id = child.href.lstrip("#")
    if not ref_id or ref_id in active_refs:
        return None
    referenced = ids.get(ref_id)
    if referenced is None:
        return None
    clone = copy.deepcopy(referenced)
    clear_ids(clone)
    _apply_use_transform(child, clone)
    _propagate_use_source(clone, getattr(child, "source", None))
    _apply_use_presentation(child, clone)
    return clone


def _apply_use_transform(child: UseNode, clone: BaseNode) -> None:
    use_transform = child.transform if child.transform is not None else Matrix.identity()
    translation = Matrix(1.0, 0.0, 0.0, 1.0, child.x, child.y)
    clone.transform = use_transform.multiply(translation).multiply(clone.transform)


def _apply_use_presentation(child: UseNode, clone: BaseNode) -> None:
    presentation_updated = _copy_use_presentation_overrides(child, clone)
    if presentation_updated:
        _resolve_clone_stroke(clone)

    if child.fill is not None and clone.fill is None:
        clone.fill = child.fill
    if child.text_style is not None and clone.text_style is None:
        clone.text_style = child.text_style


def _copy_use_presentation_overrides(child: UseNode, clone: BaseNode) -> bool:
    if not child.presentation or not clone.presentation:
        return False
    new_presentation = clone.presentation
    updated = False
    if child.presentation.stroke is not None:
        new_presentation = replace(new_presentation, stroke=child.presentation.stroke)
        updated = True
    if child.presentation.stroke_width is not None:
        new_presentation = replace(new_presentation, stroke_width=child.presentation.stroke_width)
        updated = True
    if child.presentation.stroke_opacity is not None:
        new_presentation = replace(new_presentation, stroke_opacity=child.presentation.stroke_opacity)
        updated = True
    if updated:
        clone.presentation = new_presentation
    return updated


def _resolve_clone_stroke(clone: BaseNode) -> None:
    stroke_style = resolve_stroke(
        clone.presentation.stroke,
        clone.presentation.stroke_width,
        clone.presentation.stroke_opacity,
        clone.presentation.opacity,
        dasharray=clone.presentation.stroke_dasharray,
        dashoffset=clone.presentation.stroke_dashoffset,
        linecap=clone.presentation.stroke_linecap,
        linejoin=clone.presentation.stroke_linejoin,
        miterlimit=clone.presentation.stroke_miterlimit,
    )
    if not (
        stroke_style.color is None
        and stroke_style.reference is None
        and stroke_style.width is None
    ):
        clone.stroke = stroke_style


__all__ = ["clear_ids", "collect_ids", "expand_use_nodes"]
