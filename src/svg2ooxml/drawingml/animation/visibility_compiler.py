"""Compile SVG display/visibility semantics into PowerPoint visibility plans."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.core.parser.xml_utils import walk
from svg2ooxml.ir.animation import AnimationDefinition
from svg2ooxml.ir.scene import Group, Scene

from .visibility_model import (
    _ANIMATION_TAGS,
    _SOURCE_ID_ATTR,
    _SYNTHETIC_PREFIX,
    CompiledVisibilityPlan,
    VisibilityInterval,
    compile_intervals_for_target,
    is_visibility_animation,
    normalized_visibility_attribute,
    plan_requires_animation,
)
from .visibility_rewrite import (
    plan_to_blink_animation,
    plan_to_noop_anchor_animations,
    plan_to_set_animations,
)

__all__ = [
    "CompiledVisibilityPlan",
    "VisibilityInterval",
    "assign_missing_visibility_source_ids",
    "compile_visibility_plans",
    "rewrite_visibility_animations",
]


def assign_missing_visibility_source_ids(
    svg_root: etree._Element,
    *,
    prefix: str = _SYNTHETIC_PREFIX,
) -> int:
    """Assign stable source identifiers to anonymous SVG elements.

    The compiler only needs a stable source identifier for mapping authored SVG
    elements onto converted IR leaves. Using ``data-svg2ooxml-source-id`` keeps
    those identifiers out of the SVG's authored ``id`` namespace.
    """

    existing_ids: set[str] = set()
    for element in walk(svg_root):
        for attr in ("id", _SOURCE_ID_ATTR):
            value = element.get(attr)
            if isinstance(value, str) and value:
                existing_ids.add(value)

    assigned = 0
    counter = 0
    for element in walk(svg_root):
        if local_name(element.tag) in _ANIMATION_TAGS:
            continue
        if element.get("id") or element.get(_SOURCE_ID_ATTR):
            continue
        synthetic_id = f"{prefix}-{counter}"
        while synthetic_id in existing_ids:
            counter += 1
            synthetic_id = f"{prefix}-{counter}"
        element.set(_SOURCE_ID_ATTR, synthetic_id)
        existing_ids.add(synthetic_id)
        assigned += 1
        counter += 1
    return assigned


def rewrite_visibility_animations(
    animations: list[AnimationDefinition],
    scene: Scene,
    svg_root: etree._Element | None,
) -> list[AnimationDefinition]:
    """Replace authored display/visibility animations with native visibility sets."""

    if svg_root is None:
        return animations

    xml_lookup = _build_xml_lookup(svg_root)
    scene_targets = _resolve_scene_targets(scene, xml_lookup)
    plans = compile_visibility_plans(animations, scene, svg_root)
    visibility_animations = [
        animation for animation in animations if is_visibility_animation(animation)
    ]

    rewritten = [
        animation for animation in animations if not is_visibility_animation(animation)
    ]
    for plan in plans:
        blink = plan_to_blink_animation(
            plan,
            visibility_animations=visibility_animations,
            xml_lookup=xml_lookup,
        )
        if blink is not None:
            rewritten.append(blink)
            continue
        rewritten.extend(plan_to_set_animations(plan))
    rewritten.extend(
        plan_to_noop_anchor_animations(
            visibility_animations=visibility_animations,
            plans=plans,
            scene_targets=scene_targets,
            xml_lookup=xml_lookup,
        )
    )
    if rewritten:
        return rewritten
    return rewritten


def compile_visibility_plans(
    animations: list[AnimationDefinition],
    scene: Scene,
    svg_root: etree._Element,
) -> list[CompiledVisibilityPlan]:
    """Compile per-shape visibility plans from authored SVG semantics."""

    visibility_animations = [
        animation for animation in animations if is_visibility_animation(animation)
    ]
    xml_lookup = _build_xml_lookup(svg_root)
    scene_targets = _resolve_scene_targets(scene, xml_lookup)
    if not scene_targets:
        return []

    animation_map: dict[tuple[str, str], list[AnimationDefinition]] = {}
    for animation in visibility_animations:
        normalized_attr = normalized_visibility_attribute(animation.target_attribute)
        if normalized_attr is None:
            continue
        animation_map.setdefault((animation.element_id, normalized_attr), []).append(animation)

    plans: list[CompiledVisibilityPlan] = []
    for target_id, target_element in scene_targets:
        intervals = compile_intervals_for_target(
            target_element=target_element,
            visibility_animations=visibility_animations,
            animation_map=animation_map,
        )
        if plan_requires_animation(intervals):
            plans.append(CompiledVisibilityPlan(target_id=target_id, intervals=intervals))
    return plans


def _build_xml_lookup(svg_root: etree._Element) -> dict[str, etree._Element]:
    lookup: dict[str, etree._Element] = {}
    for element in walk(svg_root):
        for attr in ("id", _SOURCE_ID_ATTR):
            value = element.get(attr)
            if isinstance(value, str) and value and value not in lookup:
                lookup[value] = element
    return lookup


def _resolve_scene_targets(
    scene: Scene,
    xml_lookup: dict[str, etree._Element],
) -> list[tuple[str, etree._Element]]:
    resolved: list[tuple[str, etree._Element]] = []
    seen: set[str] = set()

    def visit(element: object) -> None:
        if isinstance(element, Group):
            for child in element.children:
                visit(child)
            return

        target_id = _select_target_id(element, xml_lookup)
        if target_id is None or target_id in seen:
            return
        target_element = xml_lookup.get(target_id)
        if target_element is None:
            return
        seen.add(target_id)
        resolved.append((target_id, target_element))

    for element in scene.elements:
        visit(element)

    return resolved


def _select_target_id(
    element: object,
    xml_lookup: dict[str, etree._Element],
) -> str | None:
    metadata = getattr(element, "metadata", None)
    metadata_ids: list[str] = []
    if isinstance(metadata, dict):
        raw_ids = metadata.get("element_ids", [])
        if isinstance(raw_ids, list):
            for value in raw_ids:
                if isinstance(value, str) and value and value not in metadata_ids:
                    metadata_ids.append(value)

    explicit_id = getattr(element, "element_id", None)
    if isinstance(explicit_id, str) and explicit_id:
        candidates = [explicit_id] + [value for value in metadata_ids if value != explicit_id]
    else:
        candidates = metadata_ids

    for candidate in candidates:
        target_element = xml_lookup.get(candidate)
        if target_element is not None and target_element.get("id") == candidate:
            return candidate
    for candidate in candidates:
        if candidate in xml_lookup:
            return candidate
    return None
