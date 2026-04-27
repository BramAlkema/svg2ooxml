"""Top-level PowerPoint animation timing tree builder."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import p_elem, p_sub

from .timing_build_list import append_build_list, strip_internal_metadata

if TYPE_CHECKING:
    from svg2ooxml.drawingml.animation.id_allocator import TimingIDs

__all__ = ["build_timing_tree"]


def build_timing_tree(
    *,
    ids: TimingIDs,
    animation_elements: list[etree._Element],
    animated_shape_ids: list[str],
) -> etree._Element:
    """Build ECMA-376 compatible ``<p:timing>`` around animation fragments."""
    timing = p_elem("timing")
    tn_lst = p_sub(timing, "tnLst")

    root_par = p_sub(tn_lst, "par")
    root_ctn = p_sub(
        root_par,
        "cTn",
        id=str(ids.root),
        dur="indefinite",
        restart="never",
        nodeType="tmRoot",
    )
    root_child_tn_lst = p_sub(root_ctn, "childTnLst")

    seq = p_sub(root_child_tn_lst, "seq", concurrent="1", nextAc="seek")
    seq_ctn = p_sub(
        seq,
        "cTn",
        id=str(ids.main_seq),
        dur="indefinite",
        nodeType="mainSeq",
    )
    main_child_tn_lst = p_sub(seq_ctn, "childTnLst")

    click_par = p_sub(main_child_tn_lst, "par")
    click_ctn = p_sub(click_par, "cTn", id=str(ids.click_group), fill="hold")
    click_st = p_sub(click_ctn, "stCondLst")
    p_sub(click_st, "cond", delay="indefinite")
    click_begin = p_sub(click_st, "cond", evt="onBegin", delay="0")
    p_sub(click_begin, "tn", val=str(ids.main_seq))
    click_child_tn_lst = p_sub(click_ctn, "childTnLst")

    for elem in animation_elements:
        click_child_tn_lst.append(elem)

    prev_cond_lst = p_sub(seq, "prevCondLst")
    prev_cond = p_sub(prev_cond_lst, "cond", evt="onPrev", delay="0")
    p_sub(p_sub(prev_cond, "tgtEl"), "sldTgt")

    next_cond_lst = p_sub(seq, "nextCondLst")
    next_cond = p_sub(next_cond_lst, "cond", evt="onNext", delay="0")
    p_sub(p_sub(next_cond, "tgtEl"), "sldTgt")

    append_build_list(
        timing,
        animation_elements=animation_elements,
        animated_shape_ids=animated_shape_ids,
    )
    strip_internal_metadata(timing)

    return timing
