"""Shared type aliases and helpers."""

from __future__ import annotations

from typing import TypedDict


class ShapeData(TypedDict):
    """Minimal shape representation used by placeholders."""

    name: str
    value: str


__all__ = ["ShapeData"]
