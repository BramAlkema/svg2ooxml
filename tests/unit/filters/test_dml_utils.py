from __future__ import annotations

from svg2ooxml.filters.utils.dml import (
    is_effect_container,
    is_effect_dag,
    is_effect_list,
    merge_effect_fragments,
)


def test_effect_container_detection_supports_list_and_dag() -> None:
    assert is_effect_list("<a:effectLst/>")
    assert not is_effect_dag("<a:effectLst/>")
    assert is_effect_dag("<a:effectDag/>")
    assert is_effect_container("<a:effectDag/>")
    assert is_effect_container("<a:effectLst/>")
    assert not is_effect_container("<a:blur/>")


def test_merge_effect_fragments_promotes_to_effect_dag_when_needed() -> None:
    merged = merge_effect_fragments(
        "<a:effectLst><a:blur/></a:effectLst>",
        "<a:effectDag><a:cont/><a:alphaModFix><a:cont/><a:effectLst><a:glow/></a:effectLst></a:alphaModFix></a:effectDag>",
    )

    assert merged.startswith("<a:effectDag")
    assert "<a:cont/>" in merged
    assert "<a:blur/>" in merged
    assert "<a:alphaModFix>" in merged
