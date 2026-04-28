"""Compound and flipbook animation oracle assembly."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from lxml import etree

from svg2ooxml.drawingml.animation.oracle_types import (
    BehaviorFragment,
    OracleSlotError,
)
from svg2ooxml.drawingml.xml_builder import NS_P


class OracleCompoundMixin:
    """Assemble compound and flipbook timing wrappers from behavior fragments."""

    def instantiate_compound(
        self,
        *,
        shape_id: str | int,
        par_id: int,
        duration_ms: int,
        delay_ms: int = 0,
        behaviors: Sequence[BehaviorFragment | tuple[str, Mapping[str, Any]]],
    ) -> etree._Element:
        """Assemble a compound ``<p:par>`` with arbitrary behavior children."""
        base = self.instantiate(
            "emph/compound",
            shape_id=shape_id,
            par_id=par_id,
            duration_ms=duration_ms,
            delay_ms=delay_ms,
        )
        child_tn_lst = base.find(f".//{{{NS_P}}}cTn/{{{NS_P}}}childTnLst")
        if child_tn_lst is None:  # pragma: no cover - template guarantees presence
            raise OracleSlotError("emph/compound template is missing <p:childTnLst>")

        for item in behaviors:
            if isinstance(item, BehaviorFragment):
                fragment = item
            else:
                name, tokens = item
                fragment = BehaviorFragment(name=name, tokens=tokens)
            for child in self._render_behavior_fragment(
                fragment,
                shape_id=shape_id,
                duration_ms=duration_ms,
            ):
                child_tn_lst.append(child)

        return base

    def instantiate_flipbook(
        self,
        *,
        frame_shape_ids: Sequence[str | int],
        par_id: int,
        duration_ms: int,
        delay_ms: int = 0,
        start_id: int = 100,
    ) -> tuple[etree._Element, list[tuple[str, int]]]:
        """Assemble a flipbook ``<p:par>`` that sequences pre-rendered frames."""
        n_frames = len(frame_shape_ids)
        if n_frames < 2:
            raise OracleSlotError("Flipbook requires at least 2 frames")

        frame_dur = duration_ms // n_frames
        ctn_id = start_id
        set_children: list[etree._Element] = []

        def _make_set(shape_id: str | int, delay: int, val: str) -> None:
            nonlocal ctn_id
            for child in self._render_behavior_fragment(
                BehaviorFragment(
                    f"flipbook_{'show' if val == 'visible' else 'hide'}",
                    {
                        ("SHOW_ID" if val == "visible" else "HIDE_ID"): str(ctn_id),
                        ("SHOW_DELAY_MS" if val == "visible" else "HIDE_DELAY_MS"): str(
                            delay
                        ),
                        "FRAME_SHAPE_ID": str(shape_id),
                    },
                ),
                shape_id=shape_id,
                duration_ms=duration_ms,
            ):
                set_children.append(child)
            ctn_id += 1

        for shape_id in frame_shape_ids[1:]:
            _make_set(shape_id, 0, "hidden")

        for index, shape_id in enumerate(frame_shape_ids):
            _make_set(shape_id, index * frame_dur, "visible")
            if index < n_frames - 1:
                _make_set(shape_id, (index + 1) * frame_dur, "hidden")

        base = self.instantiate(
            "emph/compound",
            shape_id=frame_shape_ids[0],
            par_id=par_id,
            duration_ms=duration_ms,
            delay_ms=delay_ms,
        )
        child_tn_lst = base.find(f".//{{{NS_P}}}cTn/{{{NS_P}}}childTnLst")
        if child_tn_lst is None:
            raise OracleSlotError("emph/compound template missing <p:childTnLst>")

        for child in set_children:
            child_tn_lst.append(child)

        bld_entries = [(str(shape_id), par_id) for shape_id in frame_shape_ids]
        return base, bld_entries


__all__ = ["OracleCompoundMixin"]
