"""Scene element indexing helpers for animation export passes."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.ir.scene import Group


@dataclass(frozen=True)
class _SceneElementIndex:
    alias_map: dict[str, tuple[str, ...]]
    element_map: dict[str, object]
    center_map: dict[str, tuple[float, float]]


def _scene_element_ids(element: object) -> tuple[str, ...]:
    metadata = getattr(element, "metadata", None)
    if not isinstance(metadata, dict):
        return ()
    return tuple(
        dict.fromkeys(
            element_id
            for element_id in metadata.get("element_ids", [])
            if isinstance(element_id, str) and element_id
        )
    )


def _iter_scene_elements(elements: Iterable[object]) -> Iterator[object]:
    for element in elements:
        yield element
        if isinstance(element, Group):
            yield from _iter_scene_elements(element.children)


def _build_element_alias_map(scene: IRScene) -> dict[str, tuple[str, ...]]:
    alias_map: dict[str, tuple[str, ...]] = {}
    for element in _iter_scene_elements(scene.elements):
        element_ids = _scene_element_ids(element)
        for element_id in element_ids:
            alias_map[element_id] = element_ids
    return alias_map


def _build_scene_element_index(scene: IRScene) -> _SceneElementIndex:
    alias_map: dict[str, tuple[str, ...]] = {}
    element_map: dict[str, object] = {}
    center_map: dict[str, tuple[float, float]] = {}

    for element in _iter_scene_elements(scene.elements):
        element_ids = _scene_element_ids(element)
        if not element_ids:
            continue

        bbox = getattr(element, "bbox", None)
        center = (
            (float(bbox.x + bbox.width / 2.0), float(bbox.y + bbox.height / 2.0))
            if bbox is not None
            else None
        )
        for element_id in element_ids:
            alias_map[element_id] = element_ids
            element_map.setdefault(element_id, element)
            if center is not None:
                center_map.setdefault(element_id, center)

    return _SceneElementIndex(
        alias_map=alias_map,
        element_map=element_map,
        center_map=center_map,
    )
