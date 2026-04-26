from __future__ import annotations

from svg2ooxml.core.export.scene_index import (
    _build_element_alias_map,
    _build_scene_element_index,
    _iter_scene_elements,
    _scene_element_ids,
)
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.scene import Group
from svg2ooxml.ir.shapes import Rectangle


def test_scene_element_ids_filters_and_dedupes_metadata_ids() -> None:
    rect = Rectangle(
        bounds=Rect(0.0, 0.0, 10.0, 10.0),
        metadata={"element_ids": ["a", "", "a", 1, "b"]},
    )

    assert _scene_element_ids(rect) == ("a", "b")


def test_iter_scene_elements_walks_nested_groups() -> None:
    child = Rectangle(bounds=Rect(0.0, 0.0, 1.0, 1.0), metadata={"element_ids": ["child"]})
    group = Group(children=[child], metadata={"element_ids": ["group"]})

    assert list(_iter_scene_elements([group])) == [group, child]


def test_build_scene_element_index_maps_aliases_elements_and_centers() -> None:
    rect = Rectangle(
        bounds=Rect(10.0, 20.0, 30.0, 40.0),
        metadata={"element_ids": ["primary", "alias"]},
    )
    scene = IRScene(elements=[rect])

    index = _build_scene_element_index(scene)

    assert _build_element_alias_map(scene) == {
        "primary": ("primary", "alias"),
        "alias": ("primary", "alias"),
    }
    assert index.alias_map["alias"] == ("primary", "alias")
    assert index.element_map["primary"] is rect
    assert index.center_map["primary"] == (25.0, 40.0)
