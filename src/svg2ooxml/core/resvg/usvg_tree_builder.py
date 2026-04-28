"""Build indexed typed usvg trees from parsed SVG documents."""

from __future__ import annotations

from .parser.options import Options
from .parser.tree import SvgDocument
from .usvg_nodes import (
    BaseNode,
    ClipPathNode,
    FilterNode,
    MarkerNode,
    MaskNode,
    PaintServerNode,
    TextNode,
    Tree,
)
from .usvg_tree_conversion import convert_node
from .usvg_tree_references import collect_ids, expand_use_nodes


def build_tree(document: SvgDocument, options: Options | None = None) -> Tree:
    root = convert_node(document.root, None, options)
    ids: dict[str, BaseNode] = {}
    collect_ids(root, ids)
    expand_use_nodes(root, ids)
    tree = _index_tree(root, ids)

    from .text.layout import build_text_layout

    build_text_layout(tree)
    return tree


def _index_tree(root: BaseNode, ids: dict[str, BaseNode]) -> Tree:
    paint_servers: dict[str, PaintServerNode] = {}
    masks: dict[str, MaskNode] = {}
    clip_paths: dict[str, ClipPathNode] = {}
    markers: dict[str, MarkerNode] = {}
    filters: dict[str, FilterNode] = {}
    text_nodes: list[TextNode] = []
    for node_id, node in ids.items():
        if isinstance(node, PaintServerNode):
            paint_servers[node_id] = node
        elif isinstance(node, MaskNode):
            masks[node_id] = node
        elif isinstance(node, ClipPathNode):
            clip_paths[node_id] = node
        elif isinstance(node, MarkerNode):
            markers[node_id] = node
        elif isinstance(node, FilterNode):
            filters[node_id] = node
        if isinstance(node, TextNode):
            text_nodes.append(node)
    return Tree(
        root=root,
        ids=ids,
        paint_servers=paint_servers,
        masks=masks,
        clip_paths=clip_paths,
        markers=markers,
        filters=filters,
        text_nodes=text_nodes,
    )


__all__ = ["build_tree"]
