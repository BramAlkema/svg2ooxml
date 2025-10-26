"""Navigation specification utilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class NavigationKind(Enum):
    EXTERNAL = "external"
    SLIDE = "slide"
    ACTION = "action"
    BOOKMARK = "bookmark"
    CUSTOM_SHOW = "custom_show"


class NavigationAction(Enum):
    NEXT = "nextslide"
    PREVIOUS = "previousslide"
    FIRST = "firstslide"
    LAST = "lastslide"
    ENDSHOW = "endshow"


@dataclass(frozen=True)
class SlideTarget:
    index: int


@dataclass(frozen=True)
class BookmarkTarget:
    name: str


@dataclass(frozen=True)
class CustomShowTarget:
    name: str


@dataclass
class NavigationSpec:
    kind: NavigationKind
    tooltip: Optional[str] = None
    visited: bool = True
    href: Optional[str] = None
    slide: Optional[SlideTarget] = None
    action: Optional[NavigationAction] = None
    bookmark: Optional[BookmarkTarget] = None
    custom_show: Optional[CustomShowTarget] = None

    def __post_init__(self) -> None:
        validators = {
            NavigationKind.EXTERNAL: self.href is not None,
            NavigationKind.SLIDE: self.slide is not None,
            NavigationKind.ACTION: self.action is not None,
            NavigationKind.BOOKMARK: self.bookmark is not None,
            NavigationKind.CUSTOM_SHOW: self.custom_show is not None,
        }
        if not validators.get(self.kind, False):
            raise ValueError(f"NavigationSpec kind '{self.kind.value}' requires matching target data")

    def as_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "kind": self.kind.value,
            "tooltip": self.tooltip,
            "visited": self.visited,
        }
        if self.href:
            payload["href"] = self.href
        if self.slide:
            payload["slide"] = {"index": self.slide.index}
        if self.action:
            payload["action"] = self.action.value
        if self.bookmark:
            payload["bookmark"] = {"name": self.bookmark.name}
        if self.custom_show:
            payload["custom_show"] = {"name": self.custom_show.name}
        return payload


def parse_svg_navigation(
    href: Optional[str],
    attrs: Dict[str, str],
    tooltip: Optional[str] = None,
) -> Optional[NavigationSpec]:
    visited = _coerce_bool(attrs.get("data-visited"), default=True)

    slide_attr = attrs.get("data-slide")
    if slide_attr:
        index = _parse_positive_int(slide_attr, "data-slide")
        return NavigationSpec(
            kind=NavigationKind.SLIDE,
            slide=SlideTarget(index=index),
            tooltip=tooltip,
            visited=visited,
        )

    jump_attr = attrs.get("data-jump")
    if jump_attr:
        action = _parse_jump_action(jump_attr)
        return NavigationSpec(
            kind=NavigationKind.ACTION,
            action=action,
            tooltip=tooltip,
            visited=visited,
        )

    bookmark_attr = attrs.get("data-bookmark")
    if bookmark_attr:
        return NavigationSpec(
            kind=NavigationKind.BOOKMARK,
            bookmark=BookmarkTarget(name=bookmark_attr),
            tooltip=tooltip,
            visited=visited,
        )

    custom_show_attr = attrs.get("data-custom-show")
    if custom_show_attr:
        return NavigationSpec(
            kind=NavigationKind.CUSTOM_SHOW,
            custom_show=CustomShowTarget(name=custom_show_attr),
            tooltip=tooltip,
            visited=visited,
        )

    if href:
        trimmed = href.strip()
        if not trimmed:
            return None
        if trimmed.startswith("#"):
            return NavigationSpec(
                kind=NavigationKind.BOOKMARK,
                bookmark=BookmarkTarget(name=trimmed[1:]),
                tooltip=tooltip,
                visited=visited,
            )
        lowered = trimmed.lower()
        if lowered.startswith("slide:"):
            index = _parse_positive_int(trimmed.split(":", 1)[1], "href slide")
            return NavigationSpec(
                kind=NavigationKind.SLIDE,
                slide=SlideTarget(index=index),
                tooltip=tooltip,
                visited=visited,
            )
        return NavigationSpec(
            kind=NavigationKind.EXTERNAL,
            href=trimmed,
            tooltip=tooltip,
            visited=visited,
        )

    return None


def _parse_positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid {name} value: {value!r}") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed


def _coerce_bool(value: Optional[str], *, default: bool) -> bool:
    if value is None:
        return default
    token = value.strip().lower()
    if token in {"true", "1", "yes", "on"}:
        return True
    if token in {"false", "0", "no", "off"}:
        return False
    return default


def _parse_jump_action(value: str) -> NavigationAction:
    token = value.strip().lower()
    mapping = {
        "next": NavigationAction.NEXT,
        "previous": NavigationAction.PREVIOUS,
        "prev": NavigationAction.PREVIOUS,
        "first": NavigationAction.FIRST,
        "last": NavigationAction.LAST,
        "endshow": NavigationAction.ENDSHOW,
    }
    try:
        return mapping[token]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported navigation action: {value!r}") from exc


__all__ = [
    "NavigationKind",
    "NavigationAction",
    "SlideTarget",
    "BookmarkTarget",
    "CustomShowTarget",
    "NavigationSpec",
    "parse_svg_navigation",
]
