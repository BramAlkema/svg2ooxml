"""Per-character SVG text positioning metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.core.ir.font_metrics import estimate_run_width
from svg2ooxml.core.ir.text.layout import (
    normalize_text_segment,
    parse_number_list,
    parse_text_length_list,
)

_MIN_OUTLINE_ROTATE_RATIO = 0.25

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from svg2ooxml.core.ir.context import IRConverterContext
    from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
    from svg2ooxml.ir.text import Run


@dataclass(frozen=True)
class PerCharacterTextLayout:
    """Flattened text plus per-character placement data."""

    text: str
    abs_x: list[float]
    abs_y: list[float]
    rotate: list[float]
    advances: list[float]

    @property
    def rotated_count(self) -> int:
        """Number of visible characters with non-zero rotation."""
        return sum(
            1
            for char, value in zip(self.text, self.rotate, strict=False)
            if char.strip() and abs(value) > 1e-9
        )

    @property
    def visible_count(self) -> int:
        """Number of non-whitespace characters in the flattened text."""
        return sum(1 for char in self.text if char.strip())

    @property
    def has_rotated_text(self) -> bool:
        return self.rotated_count > 0

    @property
    def has_dense_rotation(self) -> bool:
        return (
            self.rotated_count / max(self.visible_count, 1) >= _MIN_OUTLINE_ROTATE_RATIO
        )

    def metadata(self) -> dict[str, list[float]]:
        """Return DrawingML text renderer metadata for positioned glyphs."""
        data: dict[str, list[float]] = {
            "abs_x": self.abs_x,
            "abs_y": self.abs_y,
        }
        if any(abs(value) > 1e-9 for value in self.rotate):
            data["rotate"] = self.rotate
        return data


@dataclass
class _Cursor:
    x: float = 0.0
    y: float = 0.0


@dataclass(frozen=True)
class _TextChunk:
    start: int
    end: int


class _RotateState:
    def __init__(
        self,
        values: list[float] | None = None,
        *,
        parent: _RotateState | None = None,
    ) -> None:
        self._values = values or []
        self._index = 0
        self._parent = parent

    def next(self) -> float:
        if self._values:
            value = self._values[min(self._index, len(self._values) - 1)]
            self._index += 1
            return value
        if self._parent is not None:
            return self._parent.next()
        return 0.0


class _PositionState:
    def __init__(
        self,
        *,
        x_values: list[float] | None = None,
        y_values: list[float] | None = None,
        dx_values: list[float] | None = None,
        dy_values: list[float] | None = None,
        parent: _PositionState | None = None,
    ) -> None:
        self._x_values = x_values
        self._y_values = y_values
        self._dx_values = dx_values
        self._dy_values = dy_values
        self._x_index = 0
        self._y_index = 0
        self._dx_index = 0
        self._dy_index = 0
        self._parent = parent

    def next_x(self) -> float | None:
        return self._next_absolute("_x_values", "_x_index")

    def next_y(self) -> float | None:
        return self._next_absolute("_y_values", "_y_index")

    def next_dx(self) -> float | None:
        return self._next_offset("_dx_values", "_dx_index")

    def next_dy(self) -> float | None:
        return self._next_offset("_dy_values", "_dy_index")

    def _next_absolute(self, values_name: str, index_name: str) -> float | None:
        values = getattr(self, values_name)
        if values is not None:
            index = getattr(self, index_name)
            if index < len(values):
                setattr(self, index_name, index + 1)
                return values[index]
            return None
        if self._parent is not None:
            return self._parent._next_absolute(values_name, index_name)
        return None

    def _next_offset(self, values_name: str, index_name: str) -> float | None:
        values = getattr(self, values_name)
        if values is not None:
            index = getattr(self, index_name)
            if index < len(values):
                setattr(self, index_name, index + 1)
                return values[index]
            return None
        if self._parent is not None:
            return self._parent._next_offset(values_name, index_name)
        return None


def collect_per_character_text_layout(
    element: etree._Element,
    *,
    run: Run,
    context: IRConverterContext,
    coord_space: CoordinateSpace | None = None,
    anchor: object = "start",
    dense_only: bool = True,
) -> PerCharacterTextLayout | None:
    """Collect nested ``text``/``tspan`` positioning into renderer metadata.

    The glyph outline renderer accepts one flat text run plus optional
    per-character absolute positions and rotations. SVG ``tspan`` positioning is
    hierarchical, so flatten that structure here while preserving rotate-list
    inheritance and whitespace consumption.
    """
    if not _has_rotate_tree(element):
        return None

    font_service = context.services.resolve("font")
    cursor = _Cursor()
    chars: list[str] = []
    abs_x: list[float] = []
    abs_y: list[float] = []
    rotate: list[float] = []
    advances: list[float] = []
    chunks: list[_TextChunk] = []
    active_chunk_start: int | None = None
    pending_space = False

    def begin_chunk() -> None:
        nonlocal active_chunk_start
        if active_chunk_start is not None and active_chunk_start < len(chars):
            chunks.append(_TextChunk(active_chunk_start, len(chars)))
        active_chunk_start = len(chars)

    def append_char(
        char: str,
        rotate_state: _RotateState,
        position_state: _PositionState,
    ) -> None:
        nonlocal cursor
        x_value = position_state.next_x()
        y_value = position_state.next_y()
        dx_value = position_state.next_dx()
        dy_value = position_state.next_dy()
        if x_value is not None:
            cursor.x = x_value
        if y_value is not None:
            cursor.y = y_value
        if dx_value is not None:
            cursor.x += dx_value
        if dy_value is not None:
            cursor.y += dy_value
        if active_chunk_start is None or x_value is not None or y_value is not None:
            begin_chunk()
        chars.append(char)
        abs_x.append(cursor.x)
        abs_y.append(cursor.y)
        rotate.append(rotate_state.next())
        advance = estimate_run_width(char, run, font_service)
        advances.append(advance)
        cursor.x += advance

    def flush_pending_space(
        rotate_state: _RotateState,
        position_state: _PositionState,
    ) -> None:
        nonlocal pending_space
        if not pending_space or not chars or chars[-1].isspace():
            pending_space = False
            return
        append_char(" ", rotate_state, position_state)
        pending_space = False

    def append_text(
        raw: str | None,
        rotate_state: _RotateState,
        position_state: _PositionState,
        *,
        preserve_space: bool,
    ) -> None:
        nonlocal pending_space
        if not raw:
            return
        leading_space = raw[:1].isspace()
        trailing_space = raw[-1:].isspace()
        if leading_space:
            pending_space = True

        segment = normalize_text_segment(raw, preserve_space=preserve_space)
        if not preserve_space:
            segment = segment.strip()
        if not segment.strip():
            if any(char.isspace() for char in raw):
                pending_space = bool(chars)
            return

        flush_pending_space(rotate_state, position_state)
        for char in segment:
            append_char(char, rotate_state, position_state)
        pending_space = trailing_space

    def visit(
        node: etree._Element,
        rotate_state: _RotateState,
        position_state: _PositionState,
        preserve_space: bool,
    ) -> None:
        xml_space = node.get("{http://www.w3.org/XML/1998/namespace}space")
        node_preserve = preserve_space or xml_space == "preserve"

        flush_before_position_reset = bool(node.get("x") or node.get("y"))
        if flush_before_position_reset:
            flush_pending_space(rotate_state, position_state)

        rotate_values = parse_number_list(node.get("rotate"))
        node_rotate_state = (
            _RotateState(rotate_values, parent=rotate_state)
            if rotate_values
            else rotate_state
        )

        font_size_pt = float(run.font_size_pt or 12.0)
        x_values = parse_text_length_list(
            node.get("x"), font_size_pt, axis="x", context=context
        )
        y_values = parse_text_length_list(
            node.get("y"), font_size_pt, axis="y", context=context
        )
        dx_values = parse_text_length_list(
            node.get("dx"), font_size_pt, axis="x", context=context
        )
        dy_values = parse_text_length_list(
            node.get("dy"), font_size_pt, axis="y", context=context
        )
        node_position_state = (
            _PositionState(
                x_values=x_values if x_values else None,
                y_values=y_values if y_values else None,
                dx_values=dx_values if dx_values else None,
                dy_values=dy_values if dy_values else None,
                parent=position_state,
            )
            if x_values or y_values or dx_values or dy_values
            else position_state
        )

        append_text(
            node.text,
            node_rotate_state,
            node_position_state,
            preserve_space=node_preserve,
        )

        for child in node:
            if pending_space and _node_has_text(child):
                flush_pending_space(node_rotate_state, node_position_state)
            visit(child, node_rotate_state, node_position_state, node_preserve)
            append_text(
                child.tail,
                node_rotate_state,
                node_position_state,
                preserve_space=node_preserve,
            )

    visit(element, _RotateState(), _PositionState(), False)
    if not chars:
        return None
    if active_chunk_start is not None and active_chunk_start < len(chars):
        chunks.append(_TextChunk(active_chunk_start, len(chars)))
    _apply_anchor_adjustment(abs_x, advances, chunks, anchor)
    _apply_coordinate_space(abs_x, abs_y, coord_space)
    layout = PerCharacterTextLayout(
        text="".join(chars),
        abs_x=abs_x,
        abs_y=abs_y,
        rotate=rotate,
        advances=advances,
    )
    if dense_only and not layout.has_dense_rotation:
        return None
    return layout


def _apply_coordinate_space(
    abs_x: list[float],
    abs_y: list[float],
    coord_space: CoordinateSpace | None,
) -> None:
    if coord_space is None:
        return
    for index, (x, y) in enumerate(zip(abs_x, abs_y, strict=False)):
        abs_x[index], abs_y[index] = coord_space.apply_point(x, y)


def _has_rotate_tree(element: etree._Element) -> bool:
    for node in element.iter():
        tag = _local_name(getattr(node, "tag", "")).lower()
        if tag not in {"text", "tspan"}:
            continue
        if node.get("rotate"):
            return True
    return False


def _apply_anchor_adjustment(
    abs_x: list[float],
    advances: list[float],
    chunks: list[_TextChunk],
    anchor: object,
) -> None:
    shift_factor = _anchor_shift_factor(anchor)
    if shift_factor <= 0.0:
        return
    for chunk in chunks:
        if chunk.start >= chunk.end:
            continue
        start_x = abs_x[chunk.start]
        end_x = abs_x[chunk.end - 1] + advances[chunk.end - 1]
        width = end_x - start_x
        if abs(width) <= 1e-9:
            continue
        shift = width * shift_factor
        for index in range(chunk.start, chunk.end):
            abs_x[index] -= shift


def _anchor_shift_factor(anchor: object) -> float:
    value = getattr(anchor, "value", anchor)
    token = str(value).strip().lower()
    if token == "middle":
        return 0.5
    if token == "end":
        return 1.0
    return 0.0


def _node_has_text(node: etree._Element) -> bool:
    if isinstance(node.text, str) and node.text.strip():
        return True
    return any(_node_has_text(child) for child in node)


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


__all__ = ["PerCharacterTextLayout", "collect_per_character_text_layout"]
