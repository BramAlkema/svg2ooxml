"""Shared types for parser-to-usvg conversion helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from svg2ooxml.common.units.conversion import ConversionContext

from .parser.options import Options
from .parser.tree import SvgNode
from .usvg_nodes import BaseNode

type BaseKwargs = dict[str, Any]
type NodeConverter = Callable[
    [SvgNode, BaseNode | None, Options | None, ConversionContext | None],
    BaseNode,
]
