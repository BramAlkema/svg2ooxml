"""Mask-specific metadata helpers for resvg clip/mask conversion."""

from __future__ import annotations

from typing import Any

from svg2ooxml.core.resvg.usvg_tree import BaseNode


def raw_region(attributes: dict[str, Any]) -> dict[str, str]:
    return {
        key: value
        for key in ("x", "y", "width", "height")
        if (value := attributes.get(key)) is not None
    }


def mask_policy_hints(hints: dict[str, Any]) -> dict[str, Any]:
    policy_hints: dict[str, Any] = {}
    if hints.get("has_raster"):
        policy_hints.setdefault("mask", {})["requires_raster"] = True
    if hints.get("unsupported_nodes"):
        policy_hints.setdefault("mask", {})["unsupported_nodes"] = tuple(
            hints["unsupported_nodes"]
        )
    return policy_hints


def child_ids(nodes: list[BaseNode]) -> tuple[str, ...]:
    return tuple(node_id for child in nodes if (node_id := getattr(child, "id", None)))


def serialized_sources(nodes: list[BaseNode]) -> tuple[str, ...]:
    return tuple(
        serialized
        for child in nodes
        if (serialized := serialize_source(child)) is not None
    )


def serialize_source(node: BaseNode) -> str | None:
    source = getattr(node, "source", None)
    if source is None:
        return None
    try:
        from lxml import etree

        return etree.tostring(source, encoding="unicode")
    except Exception:
        return None
